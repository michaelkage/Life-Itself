"""Deterministic evidence ledger for NPC beliefs.

This module tracks confidence in explicit claims from attributed evidence. It is
not a truth oracle: evidence strength and source reliability are simulation inputs.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


def _unit_interval(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class Evidence:
    """One piece of evidence for or against a named claim.

    direction is +1 for support and -1 for contradiction. reliability and
    strength are separate [0, 1] inputs so provenance and clarity remain visible.
    """

    evidence_id: str
    claim_id: str
    source_id: str
    direction: int
    strength: float
    source_reliability: float
    observed_tick: int

    def __post_init__(self) -> None:
        for name in ("evidence_id", "claim_id", "source_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError("direction must be +1 or -1")
        _unit_interval("strength", self.strength)
        _unit_interval("source_reliability", self.source_reliability)
        if isinstance(self.observed_tick, bool) or not isinstance(self.observed_tick, int) or self.observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")


@dataclass(frozen=True)
class BeliefState:
    claim_id: str
    confidence: float
    evidence_ids: tuple[str, ...]
    last_updated_tick: int


class BeliefLedger:
    """Stores reproducible claim confidence using bounded evidence updates.

    Each unique evidence item adjusts confidence toward 1 (support) or 0
    (contradiction) by strength * source reliability. Evidence is processed in
    (tick, evidence_id) order, making batch insertion order irrelevant.
    Reusing an evidence ID with different content is rejected.
    """

    def __init__(self, initial_confidence: dict[str, float] | None = None) -> None:
        self._confidence: dict[str, float] = {}
        self._evidence: dict[str, Evidence] = {}
        self._claim_evidence: dict[str, set[str]] = {}
        self._last_tick: dict[str, int] = {}
        for claim_id, confidence in (initial_confidence or {}).items():
            if not isinstance(claim_id, str) or not claim_id.strip():
                raise ValueError("claim IDs must be non-empty strings")
            _unit_interval("initial confidence", confidence)
            self._confidence[claim_id] = float(confidence)
            self._claim_evidence[claim_id] = set()
            self._last_tick[claim_id] = 0

    def add(self, evidence: Evidence) -> BeliefState:
        existing = self._evidence.get(evidence.evidence_id)
        if existing is not None:
            if existing != evidence:
                raise ValueError(f"evidence ID reused with different content: {evidence.evidence_id}")
            return self.get(evidence.claim_id)
        self._evidence[evidence.evidence_id] = evidence
        self._rebuild_claim(evidence.claim_id)
        return self.get(evidence.claim_id)

    def add_many(self, evidence_items: Iterable[Evidence]) -> tuple[BeliefState, ...]:
        items = tuple(evidence_items)
        ids: set[str] = set()
        for item in items:
            if item.evidence_id in ids:
                raise ValueError(f"duplicate evidence ID in batch: {item.evidence_id}")
            ids.add(item.evidence_id)
            existing = self._evidence.get(item.evidence_id)
            if existing is not None and existing != item:
                raise ValueError(f"evidence ID reused with different content: {item.evidence_id}")
        for item in sorted(items, key=lambda item: (item.observed_tick, item.evidence_id)):
            self.add(item)
        return tuple(self.get(claim_id) for claim_id in sorted({item.claim_id for item in items}))

    def get(self, claim_id: str) -> BeliefState:
        if claim_id not in self._confidence:
            raise KeyError(claim_id)
        return BeliefState(
            claim_id=claim_id,
            confidence=self._confidence[claim_id],
            evidence_ids=tuple(sorted(self._claim_evidence.get(claim_id, set()))),
            last_updated_tick=self._last_tick.get(claim_id, 0),
        )

    def snapshot(self) -> tuple[BeliefState, ...]:
        return tuple(self.get(claim_id) for claim_id in sorted(self._confidence))

    def _rebuild_claim(self, claim_id: str) -> None:
        evidence = sorted(
            (item for item in self._evidence.values() if item.claim_id == claim_id),
            key=lambda item: (item.observed_tick, item.evidence_id),
        )
        # An explicitly supplied prior is the baseline. Claims without a prior
        # start at 0.5 (unknown), then replay all evidence in canonical order.
        confidence = self._initial_confidence(claim_id)
        for item in evidence:
            influence = item.strength * item.source_reliability
            target = 1.0 if item.direction > 0 else 0.0
            confidence += (target - confidence) * influence
        self._confidence[claim_id] = min(1.0, max(0.0, confidence))
        self._claim_evidence[claim_id] = {item.evidence_id for item in evidence}
        if evidence:
            self._last_tick[claim_id] = max(item.observed_tick for item in evidence)

    def _initial_confidence(self, claim_id: str) -> float:
        return getattr(self, "_priors", {}).get(claim_id, 0.5)
