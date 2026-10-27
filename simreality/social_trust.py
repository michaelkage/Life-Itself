"""Deterministic NPC-specific social trust from explicit interaction history.

Trust is observer-specific and target-specific. This is a bounded heuristic, not
an objective verdict about a person; callers supply the meaning and strength of
an interaction, while the ledger replays history in canonical order.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


def _unit(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class SocialInteraction:
    """One observed interaction affecting an observer's trust in a target.

    direction is +1 for trust-building and -1 for trust-damaging. Strength
    represents the event's importance, not a universal moral judgment.
    """

    interaction_id: str
    observer_id: str
    target_id: str
    direction: int
    strength: float
    observed_tick: int
    context: str = "general"

    def __post_init__(self) -> None:
        for name in ("interaction_id", "observer_id", "target_id", "context"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.observer_id == self.target_id:
            raise ValueError("an NPC cannot be its own trust target")
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError("direction must be +1 or -1")
        _unit("strength", self.strength)
        if isinstance(self.observed_tick, bool) or not isinstance(self.observed_tick, int) or self.observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")


@dataclass(frozen=True)
class SocialTrustState:
    observer_id: str
    target_id: str
    trust: float
    interaction_ids: tuple[str, ...]
    last_updated_tick: int

    @property
    def source_reliability(self) -> float:
        """Expose trust as an explicit [0, 1] reliability input for belief updates."""
        return self.trust


class SocialTrustLedger:
    """Track trust per observer-target pair with deterministic event replay.

    A trust-building event moves trust toward 1; a trust-damaging event moves it
    toward 0 by a fraction equal to its strength. Default prior is 0.5. The same
    event ID/content is idempotent; conflicting reuse is rejected. Trust does not
    decay merely because time passes—decay policy can be layered on explicitly.
    """

    def __init__(self, initial_trust: dict[tuple[str, str], float] | None = None) -> None:
        self._priors: dict[tuple[str, str], float] = {}
        self._trust: dict[tuple[str, str], float] = {}
        self._interactions: dict[str, SocialInteraction] = {}
        self._last_tick: dict[tuple[str, str], int] = {}
        for pair, trust in (initial_trust or {}).items():
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("initial trust keys must be (observer_id, target_id) tuples")
            observer, target = pair
            if not all(isinstance(x, str) and x.strip() for x in pair) or observer == target:
                raise ValueError("initial trust requires distinct non-empty observer and target IDs")
            _unit("initial trust", trust)
            self._priors[pair] = float(trust)
            self._trust[pair] = float(trust)
            self._last_tick[pair] = 0

    def add(self, interaction: SocialInteraction) -> SocialTrustState:
        existing = self._interactions.get(interaction.interaction_id)
        if existing is not None:
            if existing != interaction:
                raise ValueError(f"interaction ID reused with different content: {interaction.interaction_id}")
            return self.get(interaction.observer_id, interaction.target_id)
        self._interactions[interaction.interaction_id] = interaction
        pair = (interaction.observer_id, interaction.target_id)
        self._rebuild(pair)
        return self.get(*pair)

    def add_many(self, interactions: Iterable[SocialInteraction]) -> tuple[SocialTrustState, ...]:
        items = tuple(interactions)
        seen: set[str] = set()
        for item in items:
            if item.interaction_id in seen:
                raise ValueError(f"duplicate interaction ID in batch: {item.interaction_id}")
            seen.add(item.interaction_id)
            existing = self._interactions.get(item.interaction_id)
            if existing is not None and existing != item:
                raise ValueError(f"interaction ID reused with different content: {item.interaction_id}")
        for item in sorted(items, key=lambda x: (x.observed_tick, x.interaction_id)):
            self.add(item)
        pairs = sorted({(x.observer_id, x.target_id) for x in items})
        return tuple(self.get(*pair) for pair in pairs)

    def get(self, observer_id: str, target_id: str) -> SocialTrustState:
        pair = (observer_id, target_id)
        if pair not in self._trust:
            raise KeyError(pair)
        ids = tuple(sorted(
            item.interaction_id for item in self._interactions.values()
            if (item.observer_id, item.target_id) == pair
        ))
        return SocialTrustState(observer_id, target_id, self._trust[pair], ids, self._last_tick.get(pair, 0))

    def snapshot(self) -> tuple[SocialTrustState, ...]:
        return tuple(self.get(*pair) for pair in sorted(self._trust))

    def _rebuild(self, pair: tuple[str, str]) -> None:
        events = sorted(
            (item for item in self._interactions.values()
             if (item.observer_id, item.target_id) == pair),
            key=lambda item: (item.observed_tick, item.interaction_id),
        )
        trust = self._priors.get(pair, 0.5)
        for item in events:
            target = 1.0 if item.direction > 0 else 0.0
            trust += (target - trust) * item.strength
        self._trust[pair] = min(1.0, max(0.0, trust))
        if events:
            self._last_tick[pair] = max(item.observed_tick for item in events)
