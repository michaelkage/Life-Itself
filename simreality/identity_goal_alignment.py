"""Explicit reassessment of NPC goals after accepted identity evolution.

Identity acceptance is evidence for reconsideration, not consent to change goals.
This adapter proposes changes only; an NPC must separately accept each proposal.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable

from .goals import GoalBook, GoalStatus
from .identity_decisions import IdentityChangeDecision


class IdentityGoalAction(str, Enum):
    PERSIST = "persist"
    REPRIORITIZE = "reprioritize"
    REFRAME = "reframe"
    ABANDON = "abandon"


@dataclass(frozen=True)
class IdentityGoalAlignmentPolicy:
    policy_id: str
    identity_axis: str
    goal_category: str
    action: IdentityGoalAction
    minimum_abs_delta: float = 0.0
    priority_delta: float = 0.0
    confidence_delta: float = 0.0
    target_category: str | None = None

    def __post_init__(self):
        for name in ("policy_id", "identity_axis", "goal_category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.action, IdentityGoalAction):
            raise TypeError("action must be an IdentityGoalAction")
        for name in ("minimum_abs_delta", "priority_delta", "confidence_delta"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.minimum_abs_delta <= 2:
            raise ValueError("minimum_abs_delta must be between 0 and 2")
        if not -1 <= self.confidence_delta <= 1:
            raise ValueError("confidence_delta must be between -1 and 1")
        if self.action == IdentityGoalAction.REFRAME:
            if not isinstance(self.target_category, str) or not self.target_category.strip():
                raise ValueError("reframe requires target_category")
        elif self.target_category is not None:
            raise ValueError("target_category is only valid for reframe")


@dataclass(frozen=True)
class IdentityGoalReviewProposal:
    identity_decision_id: str
    event_id: str
    owner_id: str
    identity_policy_id: str
    identity_axis: str
    identity_delta: float
    goal_id: str
    policy_id: str
    action: IdentityGoalAction
    proposed_tick: int
    current_category: str
    proposed_category: str
    current_priority: float
    proposed_priority: float
    current_confidence: float
    proposed_confidence: float

    @property
    def proposal_id(self):
        return f"{self.identity_decision_id}:{self.goal_id}:{self.policy_id}"


@dataclass(frozen=True)
class IdentityGoalReviewDecision:
    decision_id: str
    proposal: IdentityGoalReviewProposal
    accepted: bool
    decision_tick: int
    rationale: str

    def __post_init__(self):
        if not isinstance(self.decision_id, str) or not self.decision_id.strip():
            raise ValueError("decision_id must be non-empty")
        if not isinstance(self.proposal, IdentityGoalReviewProposal):
            raise TypeError("proposal must be IdentityGoalReviewProposal")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < self.proposal.proposed_tick:
            raise ValueError("decision_tick must not precede the proposal")
        if not isinstance(self.rationale, str):
            raise TypeError("rationale must be a string")


class IdentityGoalAlignmentAdapter:
    """Create deterministic goal-review proposals from accepted identity decisions."""

    def __init__(self, goals: GoalBook, policies: Iterable[IdentityGoalAlignmentPolicy]):
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        items = tuple(policies)
        if any(not isinstance(p, IdentityGoalAlignmentPolicy) for p in items):
            raise TypeError("policies must contain IdentityGoalAlignmentPolicy values")
        if len({p.policy_id for p in items}) != len(items):
            raise ValueError("policy IDs must be unique")
        self.goals = goals
        self.policies = tuple(sorted(items, key=lambda p: p.policy_id))

    def assess(self, identity_decisions: Iterable[IdentityChangeDecision], *, current_tick: int):
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        decisions = tuple(identity_decisions)
        if any(not isinstance(d, IdentityChangeDecision) for d in decisions):
            raise TypeError("identity_decisions must contain IdentityChangeDecision values")
        if len({d.decision_id for d in decisions}) != len(decisions):
            raise ValueError("identity decision IDs must be unique within a batch")
        proposals = []
        for decision in sorted(decisions, key=lambda d: (d.decision_tick, d.decision_id)):
            # Rejected identity changes are intentionally inert: no goal proposal.
            if not decision.accepted:
                continue
            if decision.decision_tick > current_tick:
                raise ValueError("identity decision occurs after the assessment tick")
            for policy in self.policies:
                if (decision.axis != policy.identity_axis
                        or abs(decision.delta) < policy.minimum_abs_delta):
                    continue
                for goal in sorted(self.goals.goals.values(), key=lambda g: g.goal_id):
                    if (goal.owner_id != decision.npc_id
                            or goal.category != policy.goal_category
                            or goal.status != GoalStatus.ACTIVE):
                        continue
                    priority = goal.priority
                    if policy.action == IdentityGoalAction.REPRIORITIZE:
                        priority = max(0.0, priority + policy.priority_delta)
                    confidence = min(1.0, max(0.0, goal.confidence + policy.confidence_delta))
                    category = policy.target_category if policy.action == IdentityGoalAction.REFRAME else goal.category
                    proposals.append(IdentityGoalReviewProposal(
                        decision.decision_id, decision.event_id, decision.npc_id,
                        decision.policy_id, decision.axis, decision.delta, goal.goal_id,
                        policy.policy_id, policy.action, current_tick, goal.category,
                        category, goal.priority, priority, goal.confidence, confidence,
                    ))
        return tuple(sorted(proposals, key=lambda p: (
            p.proposed_tick, p.owner_id, p.goal_id, p.identity_decision_id, p.policy_id
        )))


class IdentityGoalReviewDecisionLedger:
    """Append-only NPC decisions; accepted goal changes are applied exactly once."""

    def __init__(self, decisions=(), applied_decision_ids=()):
        self._decisions = {}
        self._proposal_index = {}
        self._applied = set(applied_decision_ids)
        for decision in sorted(tuple(decisions), key=lambda d: (d.decision_tick, d.decision_id)):
            self.record(decision)
        if not self._applied.issubset(self._decisions):
            raise ValueError("applied decision IDs must exist in decision history")
        if any(not self._decisions[key].accepted for key in self._applied):
            raise ValueError("rejected decisions cannot be marked applied")

    def record(self, decision):
        if not isinstance(decision, IdentityGoalReviewDecision):
            raise TypeError("decision must be IdentityGoalReviewDecision")
        old = self._decisions.get(decision.decision_id)
        if old is not None:
            if old != decision:
                raise ValueError("decision ID reused with different content")
            return old
        key = decision.proposal.proposal_id
        if key in self._proposal_index:
            raise ValueError("goal proposal already has a decision")
        self._decisions[decision.decision_id] = decision
        self._proposal_index[key] = decision.decision_id
        return decision

    def entries(self):
        return tuple(sorted(self._decisions.values(), key=lambda d: (d.decision_tick, d.decision_id)))

    def apply_accepted(self, decision_id, goals: GoalBook):
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        decision = self._decisions[decision_id]
        if not decision.accepted:
            raise ValueError("rejected goal decisions cannot be applied")
        if decision_id in self._applied:
            return False
        proposal = decision.proposal
        goal = goals.goals.get(proposal.goal_id)
        if goal is None or goal.owner_id != proposal.owner_id:
            raise ValueError("proposal goal is missing or owned by another NPC")
        if (goal.status != GoalStatus.ACTIVE
                or goal.category != proposal.current_category
                or not math.isclose(goal.priority, proposal.current_priority, abs_tol=1e-12)
                or not math.isclose(goal.confidence, proposal.current_confidence, abs_tol=1e-12)):
            raise ValueError("goal changed after proposal; reassessment is stale")
        if proposal.action == IdentityGoalAction.REPRIORITIZE:
            goal.priority = proposal.proposed_priority
        elif proposal.action == IdentityGoalAction.REFRAME:
            goal.category = proposal.proposed_category
        elif proposal.action == IdentityGoalAction.ABANDON:
            goals.set_status(goal.goal_id, GoalStatus.ABANDONED)
        goal.confidence = proposal.proposed_confidence
        goal.review_tick = max(goal.review_tick, decision.decision_tick)
        self._applied.add(decision_id)
        return True

    def is_applied(self, decision_id):
        return decision_id in self._applied


@dataclass(frozen=True)
class IdentityGoalReviewSnapshot:
    records: tuple[tuple[object, ...], ...]
    applied_decision_ids: tuple[str, ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger: IdentityGoalReviewDecisionLedger):
        if not isinstance(ledger, IdentityGoalReviewDecisionLedger):
            raise TypeError("ledger must be IdentityGoalReviewDecisionLedger")
        records = []
        for item in ledger.entries():
            p = item.proposal
            records.append((
                item.decision_id, item.accepted, item.decision_tick, item.rationale,
                p.identity_decision_id, p.event_id, p.owner_id, p.identity_policy_id,
                p.identity_axis, p.identity_delta, p.goal_id, p.policy_id, p.action.value,
                p.proposed_tick, p.current_category, p.proposed_category,
                p.current_priority, p.proposed_priority, p.current_confidence,
                p.proposed_confidence,
            ))
        return cls(tuple(sorted(records, key=lambda row: row[0])),
                   tuple(sorted(ledger._applied)))

    def __post_init__(self):
        if not isinstance(self.records, tuple) or not isinstance(self.applied_decision_ids, tuple):
            raise ValueError("snapshot collections must be tuples")
        ids = tuple(row[0] for row in self.records if isinstance(row, tuple) and row)
        if len(ids) != len(self.records) or ids != tuple(sorted(ids)) or len(set(ids)) != len(ids):
            raise ValueError("snapshot decision IDs must be unique and sorted")
        for row in self.records:
            if len(row) != 20:
                raise ValueError("invalid identity-goal decision record")
            proposal = IdentityGoalReviewProposal(
                row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11],
                IdentityGoalAction(row[12]), row[13], row[14], row[15], row[16],
                row[17], row[18], row[19],
            )
            IdentityGoalReviewDecision(row[0], proposal, row[1], row[2], row[3])
        if self.applied_decision_ids != tuple(sorted(set(self.applied_decision_ids))):
            raise ValueError("applied decision IDs must be unique and sorted")
        if not set(self.applied_decision_ids).issubset(ids):
            raise ValueError("applied IDs must reference saved decisions")
        if any(not next(row[1] for row in self.records if row[0] == key)
               for key in self.applied_decision_ids):
            raise ValueError("rejected decisions cannot be marked applied")

    def to_json(self):
        import json
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "records": [list(row) for row in self.records],
                           "applied_decision_ids": list(self.applied_decision_ids)},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        import json
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported identity-goal snapshot schema")
            result = cls(tuple(tuple(row) for row in raw["records"]),
                         tuple(raw["applied_decision_ids"]))
            if result.to_json() != payload:
                raise ValueError("identity-goal snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid identity-goal snapshot") from exc

    def restore(self):
        decisions = []
        for row in self.records:
            proposal = IdentityGoalReviewProposal(
                row[4], row[5], row[6], row[7], row[8], row[9], row[10], row[11],
                IdentityGoalAction(row[12]), row[13], row[14], row[15], row[16],
                row[17], row[18], row[19],
            )
            decisions.append(IdentityGoalReviewDecision(row[0], proposal, row[1], row[2], row[3]))
        return IdentityGoalReviewDecisionLedger(decisions, self.applied_decision_ids)
