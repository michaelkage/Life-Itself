"""Evidence-grounded emotional-scar proposals with explicit NPC acceptance.

The adapter proposes persistent scars only from an existing autobiographical
memory contribution. Proposals never mutate the scar ledger. An explicit,
owner-scoped decision records acceptance or rejection; only acceptance creates
a persistent scar.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .emotional_memory import EmotionalMemoryResponse
from .emotional_scars import EmotionalScar, NPCEmotionalScarLedger
from .npc_life_history import NPCLifeHistory


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _unit(name, value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or value > 1 or (positive and value == 0):
        raise ValueError(f"{name} must be in {'(0, 1]' if positive else '[0, 1]'}")
    return float(value)


@dataclass(frozen=True)
class EmotionalScarProposal:
    proposal_id: str
    owner_id: str
    source_event_id: str
    source_memory_id: str
    proposed_tick: int
    emotion_axis: str
    cue_id: str
    proposed_severity: float
    retained_per_tick: float = 0.999

    def __post_init__(self):
        for name in ("proposal_id", "owner_id", "source_event_id", "source_memory_id",
                     "emotion_axis", "cue_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if isinstance(self.proposed_tick, bool) or not isinstance(self.proposed_tick, int) or self.proposed_tick < 0:
            raise ValueError("proposed_tick must be a non-negative integer")
        object.__setattr__(self, "proposed_severity", _unit("proposed_severity", self.proposed_severity))
        object.__setattr__(self, "retained_per_tick", _unit("retained_per_tick", self.retained_per_tick, positive=True))


@dataclass(frozen=True)
class EmotionalScarDecision:
    decision_id: str
    proposal_id: str
    owner_id: str
    decision_tick: int
    accepted: bool
    rationale: str

    def __post_init__(self):
        for name in ("decision_id", "proposal_id", "owner_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < 0:
            raise ValueError("decision_tick must be a non-negative integer")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        if not isinstance(self.rationale, str):
            raise TypeError("rationale must be a string")


@dataclass(frozen=True)
class EmotionalScarFormationPolicy:
    policy_id: str
    minimum_intensity: float = 0.65
    severity_scale: float = 0.75
    retained_per_tick: float = 0.999

    def __post_init__(self):
        object.__setattr__(self, "policy_id", _text("policy_id", self.policy_id))
        object.__setattr__(self, "minimum_intensity", _unit("minimum_intensity", self.minimum_intensity))
        object.__setattr__(self, "severity_scale", _unit("severity_scale", self.severity_scale))
        object.__setattr__(self, "retained_per_tick", _unit("retained_per_tick", self.retained_per_tick, positive=True))


class EmotionalScarFormationAdapter:
    """Turn sufficiently strong, memory-grounded appraisal into proposals."""

    @staticmethod
    def propose(history: NPCLifeHistory, response: EmotionalMemoryResponse,
                policy: EmotionalScarFormationPolicy):
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be NPCLifeHistory")
        if not isinstance(response, EmotionalMemoryResponse):
            raise TypeError("response must be EmotionalMemoryResponse")
        if not isinstance(policy, EmotionalScarFormationPolicy):
            raise TypeError("policy must be EmotionalScarFormationPolicy")
        memories = {m.memory_id: m for m in history.memories(response.owner_id)}
        proposals = []
        for item in response.contributions:
            if item.intensity < policy.minimum_intensity:
                continue
            memory = memories.get(item.memory_id)
            if memory is None:
                raise ValueError("emotional response contribution is not owned by response owner")
            if memory.tick > response.sampled_tick:
                raise ValueError("source memory is from after emotional appraisal")
            severity = min(1.0, item.intensity * policy.severity_scale)
            if severity <= 0:
                continue
            # Stable identity means replaying the same appraisal cannot create
            # a second proposal for the same owner, memory, cue, axis and policy.
            key = "|".join((policy.policy_id, response.owner_id, item.memory_id,
                            item.cue_id, item.emotion_axis))
            proposal_id = "scar-proposal:" + str(__import__("hashlib").sha256(key.encode()).hexdigest()[:24])
            proposals.append(EmotionalScarProposal(
                proposal_id, response.owner_id, memory.event_id, memory.memory_id,
                response.sampled_tick, item.emotion_axis, item.cue_id,
                severity, policy.retained_per_tick,
            ))
        return tuple(sorted(proposals, key=lambda p: p.proposal_id))


class EmotionalScarDecisionLedger:
    """Append-only NPC decisions; acceptance alone materializes a scar."""

    def __init__(self, scar_ledger: NPCEmotionalScarLedger | None = None,
                 proposals=(), decisions=()):
        if scar_ledger is not None and not isinstance(scar_ledger, NPCEmotionalScarLedger):
            raise TypeError("scar_ledger must be NPCEmotionalScarLedger or None")
        self.scars = scar_ledger or NPCEmotionalScarLedger()
        self._proposals = {}
        self._decisions = {}
        self._proposal_decisions = {}
        for proposal in sorted(tuple(proposals), key=lambda p: (p.proposed_tick, p.proposal_id)):
            self.add_proposal(proposal)
        for decision in sorted(tuple(decisions), key=lambda d: (d.decision_tick, d.decision_id)):
            self.decide(decision)

    def proposals(self, owner_id=None):
        values = self._proposals.values()
        if owner_id is not None:
            values = (p for p in values if p.owner_id == owner_id)
        return tuple(sorted(values, key=lambda p: (p.proposed_tick, p.proposal_id)))

    def decisions(self, owner_id=None):
        values = self._decisions.values()
        if owner_id is not None:
            values = (d for d in values if d.owner_id == owner_id)
        return tuple(sorted(values, key=lambda d: (d.decision_tick, d.decision_id)))

    def add_proposal(self, proposal):
        if not isinstance(proposal, EmotionalScarProposal):
            raise TypeError("proposal must be EmotionalScarProposal")
        prior = self._proposals.get(proposal.proposal_id)
        if prior is not None:
            if prior != proposal:
                raise ValueError("proposal ID reused with conflicting content")
            return prior
        if proposal.proposed_tick < self.scars.current_tick:
            raise ValueError("proposal tick cannot precede scar ledger current_tick")
        self._proposals[proposal.proposal_id] = proposal
        return proposal

    def decide(self, decision):
        if not isinstance(decision, EmotionalScarDecision):
            raise TypeError("decision must be EmotionalScarDecision")
        prior = self._decisions.get(decision.decision_id)
        if prior is not None:
            if prior != decision:
                raise ValueError("decision ID reused with conflicting content")
            return prior
        proposal = self._proposals.get(decision.proposal_id)
        if proposal is None:
            raise KeyError(decision.proposal_id)
        if decision.owner_id != proposal.owner_id:
            raise ValueError("only the proposal's NPC owner may decide")
        if decision.decision_tick < proposal.proposed_tick or decision.decision_tick < self.scars.current_tick:
            raise ValueError("decision tick precedes proposal or ledger time")
        if proposal.proposal_id in self._proposal_decisions:
            raise ValueError("proposal already has an explicit decision")
        if decision.accepted:
            self.scars.add_scar(EmotionalScar(
                "scar:" + proposal.proposal_id, proposal.owner_id,
                proposal.source_event_id, proposal.source_memory_id,
                decision.decision_tick, proposal.emotion_axis, proposal.cue_id,
                proposal.proposed_severity, proposal.retained_per_tick,
            ))
        self._decisions[decision.decision_id] = decision
        self._proposal_decisions[proposal.proposal_id] = decision.decision_id
        return decision

    def snapshot(self):
        def proposal(p):
            return {name: getattr(p, name) for name in (
                "proposal_id", "owner_id", "source_event_id", "source_memory_id",
                "proposed_tick", "emotion_axis", "cue_id", "proposed_severity", "retained_per_tick")}
        def decision(d):
            return {name: getattr(d, name) for name in (
                "decision_id", "proposal_id", "owner_id", "decision_tick", "accepted", "rationale")}
        return {
            "version": 1, "proposals": [proposal(p) for p in self.proposals()],
            "decisions": [decision(d) for d in self.decisions()],
            "scars": self.scars.snapshot(),
        }

    @classmethod
    def from_snapshot(cls, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported emotional scar decision snapshot")
        ledger = NPCEmotionalScarLedger.from_snapshot(data["scars"])
        result = cls(ledger,
                     tuple(EmotionalScarProposal(**p) for p in data.get("proposals", ())),
                     tuple(EmotionalScarDecision(**d) for d in data.get("decisions", ())))
        if result.snapshot() != data:
            raise ValueError("emotional scar decision snapshot is not canonical")
        return result


@dataclass(frozen=True)
class EmotionalScarDecisionSnapshot:
    payload: str

    def __post_init__(self):
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        restored = EmotionalScarDecisionLedger.from_snapshot(json.loads(self.payload))
        canonical = json.dumps(restored.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise ValueError("decision snapshot must use canonical JSON")

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, EmotionalScarDecisionLedger):
            raise TypeError("ledger must be EmotionalScarDecisionLedger")
        return cls(json.dumps(ledger.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))

    @classmethod
    def from_json(cls, payload):
        return cls(payload)

    def restore(self):
        return EmotionalScarDecisionLedger.from_snapshot(json.loads(self.payload))

    def to_json(self):
        return self.payload
