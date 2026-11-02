"""Append-only, replay-safe records of NPC goal-review decisions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .goal_review import GoalReviewAction, GoalReviewProposal


@dataclass(frozen=True)
class GoalReviewDecision:
    decision_id: str
    event_id: str
    owner_id: str
    goal_id: str
    policy_id: str
    action: GoalReviewAction
    accepted: bool
    decision_tick: int
    rationale: str
    current_category: str
    proposed_category: str
    current_priority: float
    proposed_priority: float
    current_confidence: float
    proposed_confidence: float

    def __post_init__(self) -> None:
        for name in ("decision_id", "event_id", "owner_id", "goal_id",
                     "policy_id", "rationale", "current_category",
                     "proposed_category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.action, GoalReviewAction):
            raise TypeError("action must be a GoalReviewAction")
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be a bool")
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < 0:
            raise ValueError("decision_tick must be a non-negative integer")
        for name in ("current_priority", "proposed_priority",
                     "current_confidence", "proposed_confidence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if not __import__("math").isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.current_priority < 0 or self.proposed_priority < 0:
            raise ValueError("priorities cannot be negative")
        if not 0 <= self.current_confidence <= 1 or not 0 <= self.proposed_confidence <= 1:
            raise ValueError("confidence values must be between 0 and 1")

    @classmethod
    def from_proposal(cls, decision_id: str, proposal: GoalReviewProposal,
                      *, accepted: bool, decision_tick: int,
                      rationale: str) -> "GoalReviewDecision":
        if not isinstance(proposal, GoalReviewProposal):
            raise TypeError("proposal must be a GoalReviewProposal")
        return cls(
            decision_id, proposal.event_id, proposal.owner_id, proposal.goal_id,
            proposal.policy_id, proposal.action, accepted, decision_tick,
            rationale, proposal.current_category, proposal.proposed_category,
            proposal.current_priority, proposal.proposed_priority,
            proposal.current_confidence, proposal.proposed_confidence,
        )


class GoalReviewDecisionLedger:
    """Record one explicit NPC decision for each event/goal/policy proposal."""

    def __init__(self, decisions: Iterable[GoalReviewDecision] = ()):
        self._decisions: dict[str, GoalReviewDecision] = {}
        self._proposal_index: dict[tuple[str, str, str], str] = {}
        self.record_many(decisions)

    @staticmethod
    def _proposal_key(decision: GoalReviewDecision) -> tuple[str, str, str]:
        return (decision.event_id, decision.goal_id, decision.policy_id)

    def record(self, decision: GoalReviewDecision) -> GoalReviewDecision:
        if not isinstance(decision, GoalReviewDecision):
            raise TypeError("decision must be a GoalReviewDecision")
        existing = self._decisions.get(decision.decision_id)
        if existing is not None:
            if existing != decision:
                raise ValueError("decision ID was reused with different content")
            return existing
        key = self._proposal_key(decision)
        previous_id = self._proposal_index.get(key)
        if previous_id is not None:
            raise ValueError("a review proposal already has a recorded decision")
        self._decisions[decision.decision_id] = decision
        self._proposal_index[key] = decision.decision_id
        return decision

    def record_many(self, decisions: Iterable[GoalReviewDecision]) -> tuple[GoalReviewDecision, ...]:
        items = tuple(decisions)
        if any(not isinstance(item, GoalReviewDecision) for item in items):
            raise TypeError("decisions must contain GoalReviewDecision values")
        if len({item.decision_id for item in items}) != len(items):
            raise ValueError("decision IDs must be unique within a batch")
        # Validate the entire batch against a temporary ledger before committing.
        trial = GoalReviewDecisionLedger()
        for item in self.entries():
            trial.record(item)
        for item in sorted(items, key=lambda value: (value.decision_tick, value.decision_id)):
            trial.record(item)
        self._decisions = trial._decisions
        self._proposal_index = trial._proposal_index
        return tuple(self._decisions[item.decision_id] for item in sorted(
            items, key=lambda value: (value.decision_tick, value.decision_id)
        ))

    def entries(self) -> tuple[GoalReviewDecision, ...]:
        return tuple(sorted(self._decisions.values(),
                            key=lambda item: (item.decision_tick, item.decision_id)))

    def get(self, decision_id: str) -> GoalReviewDecision | None:
        return self._decisions.get(decision_id)

    def decided_proposals(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(sorted(self._proposal_index))
