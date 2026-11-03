"""Explicit, replay-safe NPC identity decisions and durable trait state."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable

from .identity_evolution import IdentityChangeProposal, NPCIdentityProfile


@dataclass(frozen=True)
class IdentityChangeDecision:
    decision_id: str
    event_id: str
    npc_id: str
    policy_id: str
    axis: str
    accepted: bool
    decision_tick: int
    rationale: str
    before: float
    proposed_after: float
    delta: float
    evidence_strength: float
    role: str

    def __post_init__(self):
        for name in ("decision_id", "event_id", "npc_id", "policy_id", "axis", "rationale"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < 0:
            raise ValueError("decision_tick must be a non-negative integer")
        if self.role not in ("participant", "witness"):
            raise ValueError("role must be participant or witness")
        for name in ("before", "proposed_after", "delta", "evidence_strength"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite numeric")
        if not -1 <= self.before <= 1 or not -1 <= self.proposed_after <= 1:
            raise ValueError("trait values must be in [-1, 1]")
        if not -1 <= self.delta <= 1 or not 0 <= self.evidence_strength <= 1:
            raise ValueError("delta or evidence strength out of bounds")
        if not math.isclose(self.proposed_after - self.before, self.delta, abs_tol=1e-12):
            raise ValueError("delta must match proposed trait change")

    @classmethod
    def from_proposal(cls, decision_id, proposal, *, accepted, decision_tick, rationale):
        if not isinstance(proposal, IdentityChangeProposal):
            raise TypeError("proposal must be IdentityChangeProposal")
        return cls(decision_id, proposal.event_id, proposal.npc_id, proposal.policy_id,
                   proposal.axis, accepted, decision_tick, rationale, proposal.before,
                   proposal.after, proposal.delta, proposal.evidence_strength, proposal.role)


class IdentityDecisionLedger:
    """Append-only decision history; accepted decisions update traits exactly once."""
    def __init__(self, profiles: Iterable[NPCIdentityProfile], decisions=()):
        profiles = tuple(profiles)
        if any(not isinstance(p, NPCIdentityProfile) for p in profiles):
            raise TypeError("profiles must contain NPCIdentityProfile values")
        if len({p.npc_id for p in profiles}) != len(profiles):
            raise ValueError("duplicate NPC identity profile")
        self._traits = {p.npc_id: dict(p.traits) for p in profiles}
        self._initial_traits = {p.npc_id: dict(p.traits) for p in profiles}
        self._sensitivities = {p.npc_id: dict(p.sensitivities or {}) for p in profiles}
        self._decisions = {}
        self._proposal_index = {}
        for decision in sorted(tuple(decisions), key=lambda item: (item.decision_tick, item.decision_id)):
            self.record(decision)

    @staticmethod
    def _key(d):
        return (d.event_id, d.npc_id, d.policy_id)

    def record(self, decision):
        if not isinstance(decision, IdentityChangeDecision):
            raise TypeError("decision must be IdentityChangeDecision")
        old = self._decisions.get(decision.decision_id)
        if old is not None:
            if old != decision:
                raise ValueError("decision ID reused with different content")
            return old
        key = self._key(decision)
        if key in self._proposal_index:
            raise ValueError("identity proposal already has a decision")
        if decision.npc_id not in self._traits or decision.axis not in self._traits[decision.npc_id]:
            raise ValueError("decision references an unknown NPC or identity axis")
        current = self._traits[decision.npc_id][decision.axis]
        if not math.isclose(current, decision.before, abs_tol=1e-12):
            raise ValueError("decision does not continue the current identity state")
        if decision.accepted:
            self._traits[decision.npc_id][decision.axis] = decision.proposed_after
        self._decisions[decision.decision_id] = decision
        self._proposal_index[key] = decision.decision_id
        return decision

    def record_many(self, decisions):
        """Atomically append a batch in deterministic decision-time order."""
        items = tuple(decisions)
        if any(not isinstance(item, IdentityChangeDecision) for item in items):
            raise TypeError("decisions must contain IdentityChangeDecision values")
        candidate = IdentityDecisionLedger(self.initial_profiles(), self.entries())
        for item in sorted(items, key=lambda d: (d.decision_tick, d.decision_id)):
            candidate.record(item)
        self._traits = candidate._traits
        self._decisions = candidate._decisions
        self._proposal_index = candidate._proposal_index
        return tuple(candidate._decisions[item.decision_id] for item in items)

    def decide(self, decision_id, proposal, *, accepted, decision_tick, rationale=""):
        return self.record(IdentityChangeDecision.from_proposal(
            decision_id, proposal, accepted=accepted, decision_tick=decision_tick,
            rationale=rationale))

    def entries(self):
        return tuple(sorted(self._decisions.values(), key=lambda d: (d.decision_tick, d.decision_id)))

    def traits_for(self, npc_id):
        if npc_id not in self._traits:
            raise KeyError(npc_id)
        return dict(sorted(self._traits[npc_id].items()))

    def initial_profiles(self):
        return tuple(NPCIdentityProfile(npc_id, dict(sorted(self._initial_traits[npc_id].items())),
                                        dict(sorted(self._sensitivities[npc_id].items())))
                     for npc_id in sorted(self._initial_traits))

    def profiles(self):
        return tuple(NPCIdentityProfile(npc_id, self.traits_for(npc_id),
                                        dict(sorted(self._sensitivities[npc_id].items())))
                     for npc_id in sorted(self._traits))


@dataclass(frozen=True)
class IdentityDecisionSnapshot:
    profiles: tuple[tuple[object, ...], ...]
    decisions: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, IdentityDecisionLedger):
            raise TypeError("ledger must be IdentityDecisionLedger")
        profiles = tuple((p.npc_id, tuple(sorted(p.traits.items())),
                          tuple(sorted((p.sensitivities or {}).items())),
                          tuple(sorted(ledger.traits_for(p.npc_id).items())))
                         for p in ledger.initial_profiles())
        decisions = tuple((d.decision_id, d.event_id, d.npc_id, d.policy_id, d.axis,
                           d.accepted, d.decision_tick, d.rationale, d.before,
                           d.proposed_after, d.delta, d.evidence_strength, d.role)
                          for d in sorted(ledger.entries(), key=lambda d: d.decision_id))
        return cls(profiles, decisions)

    def __post_init__(self):
        if not isinstance(self.profiles, tuple) or not isinstance(self.decisions, tuple):
            raise ValueError("snapshot collections must be tuples")
        ids = [p[0] for p in self.profiles]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("profile IDs must be unique and sorted")
        for p in self.profiles:
            if len(p) != 4:
                raise ValueError("invalid identity profile record")
            NPCIdentityProfile(p[0], dict(p[1]), dict(p[2]))
            NPCIdentityProfile(p[0], dict(p[3]), dict(p[2]))
        decision_ids = [d[0] for d in self.decisions]
        if decision_ids != sorted(decision_ids) or len(decision_ids) != len(set(decision_ids)):
            raise ValueError("decision IDs must be unique and sorted")
        # Rebuild to validate decisions and ensure accepted history produces saved traits.
        ledger = IdentityDecisionLedger(tuple(NPCIdentityProfile(p[0], dict(p[1]), dict(p[2]))
                                              for p in self.profiles))
        for d in self.decisions:
            if len(d) != 13:
                raise ValueError("invalid identity decision record")
        for d in sorted(self.decisions, key=lambda item: (item[6], item[0])):
            ledger.record(IdentityChangeDecision(*d))
        expected = tuple((p.npc_id, tuple(sorted(p.traits.items())),
                          tuple(sorted((p.sensitivities or {}).items()))) for p in ledger.profiles())
        expected_current = tuple((p[0], tuple(sorted(ledger.traits_for(p[0]).items()))) for p in self.profiles)
        stored_current = tuple((p[0], p[3]) for p in self.profiles)
        if expected_current != stored_current:
            raise ValueError("saved identity traits disagree with decision history")

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "profiles": [[p[0], [list(x) for x in p[1]], [list(x) for x in p[2]], [list(x) for x in p[3]]]
                                        for p in self.profiles],
                           "decisions": [list(d) for d in self.decisions]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported identity snapshot schema")
            profiles = tuple((p[0], tuple(tuple(x) for x in p[1]), tuple(tuple(x) for x in p[2]), tuple(tuple(x) for x in p[3]))
                             for p in raw["profiles"])
            result = cls(profiles, tuple(tuple(d) for d in raw["decisions"]))
            if result.to_json() != payload:
                raise ValueError("identity snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid identity snapshot") from exc

    def restore(self):
        profiles = tuple(NPCIdentityProfile(p[0], dict(p[1]), dict(p[2])) for p in self.profiles)
        decisions = tuple(IdentityChangeDecision(*d) for d in sorted(self.decisions, key=lambda item: (item[6], item[0])))
        return IdentityDecisionLedger(profiles, decisions)
