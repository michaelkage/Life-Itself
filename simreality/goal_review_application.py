"""Explicit, replay-safe application of accepted NPC goal-review decisions."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .goal_review import GoalReviewAction
from .goal_review_decisions import GoalReviewDecision
from .goals import GoalBook, GoalStatus
from .npc_goal_emergence import GoalLifecycleLedger


@dataclass(frozen=True)
class GoalReviewApplication:
    decision_id: str
    goal_id: str
    owner_id: str
    applied_tick: int
    action: GoalReviewAction
    resulting_category: str
    resulting_priority: float
    resulting_confidence: float
    resulting_status: GoalStatus

    def __post_init__(self) -> None:
        for name in ("decision_id", "goal_id", "owner_id", "resulting_category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.applied_tick, bool) or not isinstance(self.applied_tick, int) or self.applied_tick < 0:
            raise ValueError("applied_tick must be a non-negative integer")
        if not isinstance(self.action, GoalReviewAction):
            raise TypeError("action must be GoalReviewAction")
        if not isinstance(self.resulting_status, GoalStatus):
            raise TypeError("resulting_status must be GoalStatus")
        for name in ("resulting_priority", "resulting_confidence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite and numeric")
        if self.resulting_priority < 0 or not 0 <= self.resulting_confidence <= 1:
            raise ValueError("resulting priority or confidence is outside its valid range")


class GoalReviewApplicationLedger:
    """Append-only idempotency ledger; only successfully applied decisions appear."""

    def __init__(self, entries: Iterable[GoalReviewApplication] = ()) -> None:
        self._entries: dict[str, GoalReviewApplication] = {}
        self.record_many(entries)

    def record(self, item: GoalReviewApplication) -> GoalReviewApplication:
        if not isinstance(item, GoalReviewApplication):
            raise TypeError("item must be GoalReviewApplication")
        prior = self._entries.get(item.decision_id)
        if prior is not None:
            if prior != item:
                raise ValueError("decision application ID reused with conflicting content")
            return prior
        self._entries[item.decision_id] = item
        return item

    def record_many(self, items: Iterable[GoalReviewApplication]) -> tuple[GoalReviewApplication, ...]:
        batch = tuple(items)
        if any(not isinstance(item, GoalReviewApplication) for item in batch):
            raise TypeError("entries must contain GoalReviewApplication values")
        if len({item.decision_id for item in batch}) != len(batch):
            raise ValueError("application decision IDs must be unique")
        trial = dict(self._entries)
        for item in batch:
            prior = trial.get(item.decision_id)
            if prior is not None and prior != item:
                raise ValueError("decision application ID reused with conflicting content")
            trial[item.decision_id] = item
        self._entries = trial
        return tuple(sorted(batch, key=lambda item: (item.applied_tick, item.decision_id)))

    def get(self, decision_id: str) -> GoalReviewApplication | None:
        return self._entries.get(decision_id)

    def entries(self) -> tuple[GoalReviewApplication, ...]:
        return tuple(sorted(self._entries.values(), key=lambda item: (item.applied_tick, item.decision_id)))


class GoalReviewApplicationAdapter:
    """Apply an accepted decision only if its reviewed goal state is still current."""

    @staticmethod
    def apply(
        decision: GoalReviewDecision,
        goals: GoalBook,
        applications: GoalReviewApplicationLedger,
        *,
        lifecycle: GoalLifecycleLedger | None = None,
    ) -> GoalReviewApplication:
        if not isinstance(decision, GoalReviewDecision):
            raise TypeError("decision must be GoalReviewDecision")
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(applications, GoalReviewApplicationLedger):
            raise TypeError("applications must be GoalReviewApplicationLedger")
        if not decision.accepted:
            raise ValueError("rejected goal-review decisions cannot be applied")
        prior = applications.get(decision.decision_id)
        if prior is not None:
            return prior
        goal = goals.goals.get(decision.goal_id)
        if goal is None:
            raise ValueError("decision references an unknown goal")
        if goal.owner_id != decision.owner_id:
            raise ValueError("decision owner does not match goal owner")
        if goal.status != GoalStatus.ACTIVE:
            raise ValueError("goal-review decision is stale: goal is not active")
        if decision.decision_tick < goal.review_tick:
            raise ValueError("goal-review decision predates the current review state")
        if (goal.category != decision.current_category
                or goal.priority != decision.current_priority
                or goal.confidence != decision.current_confidence):
            raise ValueError("goal-review decision is stale: reviewed goal values changed")

        old = (goal.category, goal.priority, goal.confidence, goal.review_tick,
               goal.status, goal.progress)
        try:
            if decision.action == GoalReviewAction.REPRIORITIZE:
                goal.priority = decision.proposed_priority
                goal.confidence = decision.proposed_confidence
            elif decision.action == GoalReviewAction.REFRAME:
                goal.category = decision.proposed_category
                goal.priority = decision.proposed_priority
                goal.confidence = decision.proposed_confidence
            elif decision.action == GoalReviewAction.PERSIST:
                goal.confidence = decision.proposed_confidence
            elif decision.action == GoalReviewAction.PAUSE:
                # PAUSE remains advisory: there is no persisted paused status yet.
                pass
            elif decision.action == GoalReviewAction.ABANDON:
                if lifecycle is None:
                    raise ValueError("abandon decisions require a GoalLifecycleLedger")
                lifecycle.transition(
                    goals, goal.goal_id, GoalStatus.ABANDONED, decision.decision_tick,
                    decision.rationale, evidence_ids=(decision.event_id,),
                )
            else:
                raise ValueError("unsupported goal-review action")
            goal.review_tick = max(goal.review_tick, decision.decision_tick)
            item = GoalReviewApplication(
                decision.decision_id, goal.goal_id, goal.owner_id,
                decision.decision_tick, decision.action, goal.category,
                goal.priority, goal.confidence, goal.status,
            )
            applications.record(item)
            return item
        except Exception:
            goal.category, goal.priority, goal.confidence, goal.review_tick, goal.status, goal.progress = old
            raise
