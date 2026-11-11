"""Evidence-based review proposals for persistently infeasible NPC goals.

A single failed plan is an observation, not a change of intention. Only
consecutive failed plans spanning a configured simulation-time window can
recommend review. Assessment is read-only; accepted decisions continue through
the established goal-review decision and application pipeline.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
from typing import Iterable

from .action_evaluation import ActionPlanEvaluationLedger
from .goal_review import GoalReviewAction, GoalReviewProposal
from .goals import GoalBook, GoalStatus
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class GoalExecutionHealthRule:
    rule_id: str
    goal_category: str
    minimum_consecutive_failures: int = 3
    minimum_observation_ticks: int = 24
    action: GoalReviewAction = GoalReviewAction.REPRIORITIZE
    priority_delta: float = -1.0
    confidence_delta: float = -0.15
    rationale: str = "Repeated plan failures indicate persistent infeasibility"

    def __post_init__(self):
        for name in ("rule_id", "goal_category", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        for name in ("minimum_consecutive_failures", "minimum_observation_ticks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.action not in {GoalReviewAction.REPRIORITIZE, GoalReviewAction.PERSIST}:
            raise ValueError("execution-health rules may only persist or reprioritize goals")
        for name in ("priority_delta", "confidence_delta"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if not -1.0 <= self.confidence_delta <= 1.0:
            raise ValueError("confidence_delta must be between -1 and 1")


@dataclass(frozen=True)
class GoalExecutionHealthProposal:
    proposal_id: str
    owner_id: str
    goal_id: str
    rule_id: str
    action: GoalReviewAction
    current_category: str
    current_priority: float
    proposed_priority: float
    current_confidence: float
    proposed_confidence: float
    consecutive_failed_plans: int
    first_failure_tick: int
    latest_failure_tick: int
    evidence_event_ids: tuple[str, ...]
    rationale: str

    def __post_init__(self):
        for name in ("proposal_id", "owner_id", "goal_id", "rule_id", "current_category", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.action not in {GoalReviewAction.REPRIORITIZE, GoalReviewAction.PERSIST}:
            raise ValueError("unsupported execution-health review action")
        if isinstance(self.consecutive_failed_plans, bool) or not isinstance(self.consecutive_failed_plans, int) or self.consecutive_failed_plans < 1:
            raise ValueError("consecutive_failed_plans must be positive")
        if (isinstance(self.first_failure_tick, bool) or not isinstance(self.first_failure_tick, int)
                or isinstance(self.latest_failure_tick, bool) or not isinstance(self.latest_failure_tick, int)
                or self.first_failure_tick < 0 or self.latest_failure_tick < self.first_failure_tick):
            raise ValueError("failure ticks are invalid")
        for name in ("current_priority", "proposed_priority", "current_confidence", "proposed_confidence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.current_priority < 0 or self.proposed_priority < 0 or not 0 <= self.current_confidence <= 1 or not 0 <= self.proposed_confidence <= 1:
            raise ValueError("goal review values are outside their valid ranges")
        if not self.evidence_event_ids or len(set(self.evidence_event_ids)) != len(self.evidence_event_ids):
            raise ValueError("evidence_event_ids must be non-empty and unique")

    def to_goal_review_proposal(self) -> GoalReviewProposal:
        """Adapt to the existing explicit decision/application pipeline."""
        return GoalReviewProposal(
            event_id=self.evidence_event_ids[-1], owner_id=self.owner_id, goal_id=self.goal_id,
            policy_id=self.rule_id, action=self.action, current_category=self.current_category,
            proposed_category=self.current_category, current_priority=self.current_priority,
            proposed_priority=self.proposed_priority, current_confidence=self.current_confidence,
            proposed_confidence=self.proposed_confidence, reason=self.rationale,
        )


class GoalExecutionHealthEvaluator:
    """Detect persistent plan infeasibility without inferring changed intentions."""

    def __init__(self, goals: GoalBook, evaluations: ActionPlanEvaluationLedger,
                 events: WorldEventLedger, rules: Iterable[GoalExecutionHealthRule]):
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(evaluations, ActionPlanEvaluationLedger):
            raise TypeError("evaluations must be ActionPlanEvaluationLedger")
        if not isinstance(events, WorldEventLedger) or evaluations.events is not events:
            raise ValueError("evaluations and evaluator must share the authoritative event journal")
        items = tuple(rules)
        if any(not isinstance(rule, GoalExecutionHealthRule) for rule in items):
            raise TypeError("rules must contain GoalExecutionHealthRule values")
        if len({rule.rule_id for rule in items}) != len(items):
            raise ValueError("rule IDs must be unique")
        self.goals, self.evaluations, self.events = goals, evaluations, events
        self.rules = tuple(sorted(items, key=lambda item: item.rule_id))

    def assess(self) -> tuple[GoalExecutionHealthProposal, ...]:
        proposals = []
        for goal in sorted(self.goals.goals.values(), key=lambda item: item.goal_id):
            if goal.status != GoalStatus.ACTIVE:
                continue
            observations = []
            for plan in self.evaluations.plan_history:
                if plan.goal_id != goal.goal_id or plan.owner_id != goal.owner_id:
                    continue
                if plan.terminal_status not in {"completed", "failed"} or not plan.evidence_event_ids:
                    continue
                ticks = [self.events.get(event_id).tick for event_id in plan.evidence_event_ids]
                observations.append((max(ticks), plan))
            observations.sort(key=lambda pair: (pair[0], pair[1].plan_id))
            streak = []
            for tick, plan in observations:
                if plan.terminal_status == "completed":
                    streak.clear()
                else:
                    streak.append((tick, plan))
            if not streak:
                continue
            first_tick, latest_tick = streak[0][0], streak[-1][0]
            evidence = tuple(dict.fromkeys(event_id for _, plan in streak for event_id in plan.evidence_event_ids))
            for rule in self.rules:
                if (goal.category != rule.goal_category
                        or len(streak) < rule.minimum_consecutive_failures
                        or latest_tick - first_tick < rule.minimum_observation_ticks
                        or latest_tick < goal.review_tick):
                    continue
                priority = max(0.0, goal.priority + rule.priority_delta) if rule.action == GoalReviewAction.REPRIORITIZE else goal.priority
                confidence = min(1.0, max(0.0, goal.confidence + rule.confidence_delta))
                proposals.append(GoalExecutionHealthProposal(
                    f"goal-execution-health:{goal.goal_id}:{rule.rule_id}:{latest_tick}",
                    goal.owner_id, goal.goal_id, rule.rule_id, rule.action, goal.category,
                    goal.priority, priority, goal.confidence, confidence, len(streak),
                    first_tick, latest_tick, evidence,
                    f"{rule.rationale} ({len(streak)} consecutive failed plans over {latest_tick - first_tick} ticks)",
                ))
        return tuple(sorted(proposals, key=lambda item: (item.latest_failure_tick, item.owner_id, item.goal_id, item.rule_id)))
