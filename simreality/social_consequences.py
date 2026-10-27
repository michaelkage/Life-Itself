"""Deterministic bridge from witnessed NPC actions to social memory.

A caller describes an observed event and explicitly supplies its social meaning.
The recorder updates the observer's trust in the actor, then records any claims
the observer took from the event. No universal moral interpretation is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .beliefs import BeliefState, Evidence
from .social_beliefs import SocialBeliefSystem
from .social_trust import SocialInteraction, SocialTrustLedger, SocialTrustState


@dataclass(frozen=True)
class ObservedClaim:
    """One claim an observer takes from an event.

    direction indicates whether the event supports (+1) or contradicts (-1)
    the claim. strength represents clarity/importance of the observation.
    """

    claim_id: str
    direction: int
    strength: float

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError("direction must be +1 or -1")
        if isinstance(self.strength, bool) or not isinstance(self.strength, (int, float)):
            raise ValueError("strength must be numeric")
        import math
        if not math.isfinite(self.strength) or not 0.0 <= self.strength <= 1.0:
            raise ValueError("strength must be finite and in [0, 1]")


@dataclass(frozen=True)
class WitnessedSocialEvent:
    """A single event as interpreted by one observer."""

    event_id: str
    observer_id: str
    actor_id: str
    observed_tick: int
    trust_direction: int
    trust_strength: float
    claims: tuple[ObservedClaim, ...] = ()

    def __post_init__(self) -> None:
        for name in ("event_id", "observer_id", "actor_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.observer_id == self.actor_id:
            raise ValueError("observer and actor must be different NPCs")
        if isinstance(self.observed_tick, bool) or not isinstance(self.observed_tick, int) or self.observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")
        if isinstance(self.trust_direction, bool) or self.trust_direction not in (-1, 1):
            raise ValueError("trust_direction must be +1 or -1")
        if isinstance(self.trust_strength, bool) or not isinstance(self.trust_strength, (int, float)):
            raise ValueError("trust_strength must be numeric")
        import math
        if not math.isfinite(self.trust_strength) or not 0.0 <= self.trust_strength <= 1.0:
            raise ValueError("trust_strength must be finite and in [0, 1]")
        if not isinstance(self.claims, tuple) or any(not isinstance(c, ObservedClaim) for c in self.claims):
            raise ValueError("claims must be a tuple of ObservedClaim records")
        ids = [c.claim_id for c in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim IDs must be unique within one witnessed event")


@dataclass(frozen=True)
class SocialConsequenceResult:
    event_id: str
    trust_state: SocialTrustState
    beliefs: tuple[BeliefState, ...]


class SocialConsequenceRecorder:
    """Apply witnessed events to trust and beliefs with idempotent replay.

    Replaying an identical event returns its original result without applying the
    trust change twice. Reusing event_id for different content is rejected.
    Event IDs for generated interactions/evidence are namespaced from event_id.
    """

    def __init__(self, trust: SocialTrustLedger, beliefs: SocialBeliefSystem) -> None:
        if not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        if beliefs.trust is not trust:
            raise ValueError("beliefs must use the same trust ledger")
        self.trust = trust
        self.beliefs = beliefs
        self._events: dict[str, WitnessedSocialEvent] = {}
        self._results: dict[str, SocialConsequenceResult] = {}

    def record(self, event: WitnessedSocialEvent) -> SocialConsequenceResult:
        if not isinstance(event, WitnessedSocialEvent):
            raise TypeError("event must be a WitnessedSocialEvent")
        prior = self._events.get(event.event_id)
        if prior is not None:
            if prior != event:
                raise ValueError(f"event ID reused with different content: {event.event_id}")
            return self._results[event.event_id]

        interaction = SocialInteraction(
            interaction_id=f"{event.event_id}:trust",
            observer_id=event.observer_id,
            target_id=event.actor_id,
            direction=event.trust_direction,
            strength=event.trust_strength,
            observed_tick=event.observed_tick,
            context="witnessed_event",
        )
        trust_state = self.trust.add(interaction)
        states = []
        for claim in sorted(event.claims, key=lambda item: item.claim_id):
            evidence = Evidence(
                evidence_id=f"{event.event_id}:claim:{claim.claim_id}",
                claim_id=claim.claim_id,
                source_id=event.actor_id,
                direction=claim.direction,
                strength=claim.strength,
                source_reliability=0.5,
                observed_tick=event.observed_tick,
            )
            states.append(self.beliefs.observe(event.observer_id, evidence))
        result = SocialConsequenceResult(event.event_id, trust_state, tuple(states))
        self._events[event.event_id] = event
        self._results[event.event_id] = result
        return result

    def snapshot(self) -> tuple[SocialConsequenceResult, ...]:
        return tuple(self._results[event_id] for event_id in sorted(self._results))
