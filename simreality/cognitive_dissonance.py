"""Explicit, observer-owned cognitive dissonance tracking for NPCs.

Conflict detection is a read-only calculation over caller-authored inputs.
Responses are explicit decisions and never mutate beliefs, values, or identity.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _unit(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class DissonanceInput:
    """One declared contradiction or commitment/action mismatch.

    kind is 'belief_conflict' or 'commitment_violation'. For belief conflicts,
    evidence_confidence is the confidence that the two declared claims conflict.
    For commitment violations, it is the confidence that the described action
    occurred. No claim semantics or world facts are inferred by this module.
    """
    conflict_id: str
    owner_id: str
    kind: str
    description: str
    left_reference: str
    right_reference: str
    commitment_strength: float
    evidence_confidence: float
    relevance: float
    tick: int

    def __post_init__(self):
        for name in ("conflict_id", "owner_id", "description", "left_reference", "right_reference"):
            _text(name, getattr(self, name))
        if self.kind not in ("belief_conflict", "commitment_violation"):
            raise ValueError("kind must be belief_conflict or commitment_violation")
        for name in ("commitment_strength", "evidence_confidence", "relevance"):
            _unit(name, getattr(self, name))
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")

    @property
    def score(self):
        return self.commitment_strength * self.evidence_confidence * self.relevance


@dataclass(frozen=True)
class DissonanceDecision:
    decision_id: str
    conflict_id: str
    owner_id: str
    response: str
    tick: int
    rationale: str

    def __post_init__(self):
        for name in ("decision_id", "conflict_id", "owner_id"):
            _text(name, getattr(self, name))
        if not isinstance(self.rationale, str):
            raise ValueError("rationale must be a string")
        if self.response not in ("rationalize", "avoid", "seek_evidence", "acknowledge", "reconsider"):
            raise ValueError("unsupported dissonance response")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")


class CognitiveDissonanceLedger:
    """Append-only conflict and response history, scoped to individual NPCs."""

    def __init__(self, conflicts=(), decisions=()):
        self._conflicts = {}
        self._decisions = {}
        self._decided_conflicts = {}
        for item in sorted(tuple(conflicts), key=lambda x: (x.tick, x.conflict_id)):
            self.record(item)
        for item in sorted(tuple(decisions), key=lambda x: (x.tick, x.decision_id)):
            self._store_decision(item)

    def record(self, item):
        if not isinstance(item, DissonanceInput):
            raise TypeError("item must be DissonanceInput")
        prior = self._conflicts.get(item.conflict_id)
        if prior is not None:
            if prior != item:
                raise ValueError("conflict ID reused with different content")
            return prior
        self._conflicts[item.conflict_id] = item
        return item

    def _store_decision(self, decision):
        if not isinstance(decision, DissonanceDecision):
            raise TypeError("decision must be DissonanceDecision")
        if decision.conflict_id not in self._conflicts:
            raise KeyError(decision.conflict_id)
        conflict = self._conflicts[decision.conflict_id]
        if conflict.owner_id != decision.owner_id or decision.tick < conflict.tick:
            raise ValueError("decision owner must match conflict and decision cannot precede it")
        prior = self._decisions.get(decision.decision_id)
        if prior is not None:
            if prior != decision:
                raise ValueError("decision ID reused with conflicting content")
            return prior
        if decision.conflict_id in self._decided_conflicts:
            raise ValueError("conflict already has a response decision")
        self._decisions[decision.decision_id] = decision
        self._decided_conflicts[decision.conflict_id] = decision.decision_id
        return decision

    def decide(self, decision_id, conflict_id, *, response, tick, rationale=""):
        _text("decision_id", decision_id)
        if conflict_id not in self._conflicts:
            raise KeyError(conflict_id)
        conflict = self._conflicts[conflict_id]
        decision = DissonanceDecision(decision_id, conflict_id, conflict.owner_id,
                                      response, tick, rationale)
        prior = self._decisions.get(decision_id)
        if prior is not None:
            if prior != decision:
                raise ValueError("decision ID reused with conflicting content")
            return prior
        return self._store_decision(decision)

    def conflicts(self, owner_id=None):
        values = self._conflicts.values()
        if owner_id is not None:
            values = (item for item in values if item.owner_id == owner_id)
        return tuple(sorted(values, key=lambda x: (x.tick, x.conflict_id)))

    def decisions(self, owner_id=None):
        values = self._decisions.values()
        if owner_id is not None:
            values = (item for item in values if item.owner_id == owner_id)
        return tuple(sorted(values, key=lambda x: (x.tick, x.decision_id)))

    def unresolved(self, owner_id):
        return tuple(item for item in self.conflicts(owner_id)
                     if item.conflict_id not in self._decided_conflicts)

    def decision_for(self, conflict_id):
        decision_id = self._decided_conflicts.get(conflict_id)
        return self._decisions.get(decision_id) if decision_id else None


@dataclass(frozen=True)
class CognitiveDissonanceSnapshot:
    conflicts: tuple[tuple[object, ...], ...]
    decisions: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, CognitiveDissonanceLedger):
            raise TypeError("ledger must be CognitiveDissonanceLedger")
        conflict_fields = ("conflict_id", "owner_id", "kind", "description",
                           "left_reference", "right_reference", "commitment_strength",
                           "evidence_confidence", "relevance", "tick")
        decision_fields = ("decision_id", "conflict_id", "owner_id", "response", "tick", "rationale")
        conflicts = tuple(tuple(getattr(x, f) for f in conflict_fields)
                          for x in sorted(ledger.conflicts(), key=lambda x: x.conflict_id))
        decisions = tuple(tuple(getattr(x, f) for f in decision_fields)
                          for x in sorted(ledger.decisions(), key=lambda x: x.decision_id))
        return cls(conflicts, decisions)

    def __post_init__(self):
        if not isinstance(self.conflicts, tuple) or any(not isinstance(x, tuple) or len(x) != 10 for x in self.conflicts):
            raise ValueError("invalid conflict snapshot")
        if not isinstance(self.decisions, tuple) or any(not isinstance(x, tuple) or len(x) != 6 for x in self.decisions):
            raise ValueError("invalid decision snapshot")
        conflict_ids = [x[0] for x in self.conflicts]
        decision_ids = [x[0] for x in self.decisions]
        if conflict_ids != sorted(set(conflict_ids)) or decision_ids != sorted(set(decision_ids)):
            raise ValueError("snapshot IDs must be unique and sorted")
        CognitiveDissonanceLedger(
            tuple(DissonanceInput(*x) for x in self.conflicts),
            tuple(DissonanceDecision(*x) for x in self.decisions),
        )

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "conflicts": [list(x) for x in self.conflicts],
                           "decisions": [list(x) for x in self.decisions]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            version = raw.get("schema_version") if isinstance(raw, dict) else None
            if isinstance(version, bool) or version != cls.SCHEMA_VERSION:
                raise ValueError("unsupported cognitive dissonance schema")
            result = cls(tuple(tuple(x) for x in raw["conflicts"]),
                         tuple(tuple(x) for x in raw["decisions"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid cognitive dissonance snapshot") from exc

    def restore(self):
        return CognitiveDissonanceLedger(
            tuple(DissonanceInput(*x) for x in self.conflicts),
            tuple(DissonanceDecision(*x) for x in self.decisions),
        )
