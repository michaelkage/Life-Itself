"""Explicit, replay-safe NPC decisions about observer-specific learning proposals.

Accepting a proposal applies one conditioning record. Rejecting it preserves the
proposal and rationale in decision history without changing learned associations.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .psychological_interpretation import LearningProposal
from .psychological_conditioning import ConditioningProfile, NPCConditioningLedger


@dataclass(frozen=True)
class PsychologicalLearningDecision:
    decision_id: str
    owner_id: str
    source_event_id: str
    rule_id: str
    cue: str
    accepted: bool
    decision_tick: int
    rationale: str
    outcome: float
    intensity: float
    mode: str

    def __post_init__(self):
        for name in ("decision_id", "owner_id", "source_event_id", "rule_id", "cue", "rationale"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < 0:
            raise ValueError("decision_tick must be a non-negative integer")
        if isinstance(self.outcome, bool) or not isinstance(self.outcome, (int, float)) or not -1 <= self.outcome <= 1:
            raise ValueError("outcome must be in [-1, 1]")
        if isinstance(self.intensity, bool) or not isinstance(self.intensity, (int, float)) or not 0 <= self.intensity <= 1:
            raise ValueError("intensity must be in [0, 1]")
        if self.mode not in ("reinforce", "extinguish"):
            raise ValueError("mode must be reinforce or extinguish")

    @classmethod
    def from_proposal(cls, decision_id, proposal, *, accepted, decision_tick, rationale=""):
        if not isinstance(proposal, LearningProposal):
            raise TypeError("proposal must be a LearningProposal")
        return cls(decision_id, proposal.owner_id, proposal.source_event_id,
                   proposal.rule_id, proposal.cue, accepted, decision_tick,
                   rationale, proposal.outcome, proposal.intensity, proposal.mode)


class PsychologicalLearningDecisionLedger:
    """Append-only decisions; accepted learning is applied exactly once."""

    def __init__(self, decisions=()):
        self._decisions = {}
        self._proposals = {}
        for decision in sorted(tuple(decisions), key=lambda d: (d.decision_tick, d.decision_id)):
            self._validate_and_store(decision)

    @staticmethod
    def _proposal_key(decision):
        return (decision.source_event_id, decision.owner_id, decision.rule_id)

    def _validate_and_store(self, decision):
        if not isinstance(decision, PsychologicalLearningDecision):
            raise TypeError("decision must be PsychologicalLearningDecision")
        existing = self._decisions.get(decision.decision_id)
        if existing is not None:
            if existing != decision:
                raise ValueError("learning decision ID reused with conflicting content")
            return existing
        key = self._proposal_key(decision)
        if key in self._proposals:
            raise ValueError("learning proposal already has a decision")
        self._decisions[decision.decision_id] = decision
        self._proposals[key] = decision.decision_id
        return decision

    def decide(self, decision_id, proposal, *, accepted, decision_tick,
               conditioning, profile, rationale=""):
        if not isinstance(conditioning, NPCConditioningLedger):
            raise TypeError("conditioning must be an NPCConditioningLedger")
        if not isinstance(profile, ConditioningProfile):
            raise TypeError("profile must be a ConditioningProfile")
        decision = PsychologicalLearningDecision.from_proposal(
            decision_id, proposal, accepted=accepted,
            decision_tick=decision_tick, rationale=rationale)
        prior = self._decisions.get(decision_id)
        if prior is not None:
            if prior != decision:
                raise ValueError("learning decision ID reused with conflicting content")
            return prior
        if profile.owner_id != decision.owner_id:
            raise ValueError("conditioning profile owner must match proposal owner")
        if decision.decision_tick < conditioning.current_tick:
            raise ValueError("decision tick cannot precede conditioning ledger clock")
        if self._proposal_key(decision) in self._proposals:
            raise ValueError("learning proposal already has a decision")
        # Apply before appending: failed conditioning leaves decision history unchanged.
        if decision.accepted:
            conditioning.learn(
                record_id=f"psych-learning:{decision.decision_id}",
                source_event_id=decision.source_event_id,
                owner_id=decision.owner_id, cue=decision.cue,
                tick=decision.decision_tick, outcome=decision.outcome,
                intensity=decision.intensity, mode=decision.mode, profile=profile)
        return self._validate_and_store(decision)

    def entries(self):
        return tuple(sorted(self._decisions.values(),
                            key=lambda d: (d.decision_tick, d.decision_id)))

    def decision_for(self, source_event_id, owner_id, rule_id):
        decision_id = self._proposals.get((source_event_id, owner_id, rule_id))
        return self._decisions.get(decision_id) if decision_id is not None else None


@dataclass(frozen=True)
class PsychologicalLearningDecisionSnapshot:
    decisions: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, PsychologicalLearningDecisionLedger):
            raise TypeError("ledger must be PsychologicalLearningDecisionLedger")
        decisions = tuple(tuple(getattr(d, field) for field in (
            "decision_id", "owner_id", "source_event_id", "rule_id", "cue",
            "accepted", "decision_tick", "rationale", "outcome", "intensity", "mode"))
            for d in sorted(ledger.entries(), key=lambda item: item.decision_id))
        return cls(decisions)

    def __post_init__(self):
        if not isinstance(self.decisions, tuple) or any(not isinstance(d, tuple) or len(d) != 11 for d in self.decisions):
            raise ValueError("invalid psychological learning decision snapshot")
        ids = [d[0] for d in self.decisions]
        if any(not isinstance(x, str) or not x.strip() for x in ids) or ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("decision IDs must be unique, non-empty, and sorted")
        ledger = PsychologicalLearningDecisionLedger(tuple(PsychologicalLearningDecision(*d) for d in self.decisions))
        if len(ledger.entries()) != len(self.decisions):
            raise ValueError("invalid psychological learning decision history")

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "decisions": [list(d) for d in self.decisions]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported psychological learning decision schema")
            result = cls(tuple(tuple(d) for d in raw["decisions"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid psychological learning decision snapshot") from exc

    def restore(self):
        return PsychologicalLearningDecisionLedger(
            tuple(PsychologicalLearningDecision(*d) for d in sorted(self.decisions, key=lambda item: (item[6], item[0]))))
