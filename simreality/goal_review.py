"""Evidence-based, read-only reassessment proposals for NPC goals.

A world event can prompt an NPC to reconsider an intention, but it does not
silently rewrite that intention. Explicit policies produce review proposals;
the owning simulation decides whether and when an NPC accepts them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable

from .goals import GoalBook, GoalStatus
from .world_events import WorldEvent


class GoalReviewAction(str, Enum):
    PERSIST = "persist"
    REPRIORITIZE = "reprioritize"
    PAUSE = "pause"
    REFRAME = "reframe"
    ABANDON = "abandon"


@dataclass(frozen=True)
class GoalReviewPolicy:
    policy_id: str
    event_type: str
    goal_category: str
    action: GoalReviewAction
    priority_delta: float = 0.0
    confidence_delta: float = 0.0
    target_category: str | None = None
    required_attributes: tuple[tuple[str, str], ...] = ()
    minimum_confidence: float = 0.0

    def __post_init__(self) -> None:
        for value in (self.policy_id, self.event_type, self.goal_category):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("policy identifiers must be non-empty")
        if not isinstance(self.action, GoalReviewAction):
            raise TypeError("action must be a GoalReviewAction")
        for name, value in (("priority_delta", self.priority_delta),
                            ("confidence_delta", self.confidence_delta),
                            ("minimum_confidence", self.minimum_confidence)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.priority_delta < 0:
            raise ValueError("priority_delta cannot be negative")
        if not -1.0 <= self.confidence_delta <= 1.0:
            raise ValueError("confidence_delta must be between -1 and 1")
        if not 0.0 <= self.minimum_confidence <= 1.0:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if self.action == GoalReviewAction.REFRAME:
            if not isinstance(self.target_category, str) or not self.target_category.strip():
                raise ValueError("reframe policies require a target_category")
        elif self.target_category is not None:
            raise ValueError("target_category is only valid for reframe policies")
        if len(set(self.required_attributes)) != len(self.required_attributes):
            raise ValueError("required attributes must be unique")
        if any(not isinstance(pair, tuple) or len(pair) != 2
               or not isinstance(pair[0], str) or not pair[0]
               or not isinstance(pair[1], str) for pair in self.required_attributes):
            raise ValueError("required attributes must be string pairs")


@dataclass(frozen=True)
class GoalReviewProposal:
    event_id: str
    owner_id: str
    goal_id: str
    policy_id: str
    action: GoalReviewAction
    current_category: str
    proposed_category: str
    current_priority: float
    proposed_priority: float
    current_confidence: float
    proposed_confidence: float
    reason: str


class GoalReviewEvaluator:
    """Turn explicit event evidence into stable proposals without mutating goals."""

    def __init__(self, goals: GoalBook, policies: Iterable[GoalReviewPolicy]):
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        items = tuple(policies)
        if any(not isinstance(policy, GoalReviewPolicy) for policy in items):
            raise TypeError("policies must contain GoalReviewPolicy values")
        if len({policy.policy_id for policy in items}) != len(items):
            raise ValueError("policy IDs must be unique")
        self.goals = goals
        self.policies = tuple(sorted(items, key=lambda policy: policy.policy_id))

    def assess(self, events: Iterable[WorldEvent]) -> tuple[GoalReviewProposal, ...]:
        items = tuple(events)
        if any(not isinstance(event, WorldEvent) for event in items):
            raise TypeError("events must contain WorldEvent values")
        if len({event.event_id for event in items}) != len(items):
            raise ValueError("event IDs must be unique within a batch")

        proposals: list[GoalReviewProposal] = []
        for event in sorted(items, key=lambda item: (item.tick, item.event_id)):
            attributes = dict(event.attributes)
            participants = set(event.participants)
            for policy in self.policies:
                if event.event_type != policy.event_type:
                    continue
                if any(attributes.get(key) != value
                       for key, value in policy.required_attributes):
                    continue
                for goal in sorted(self.goals.goals.values(), key=lambda item: item.goal_id):
                    if (goal.owner_id not in participants
                            or goal.category != policy.goal_category
                            or goal.status != GoalStatus.ACTIVE
                            or goal.confidence < policy.minimum_confidence
                            or event.tick < goal.review_tick):
                        continue
                    priority = goal.priority
                    confidence = min(1.0, max(0.0,
                        goal.confidence + policy.confidence_delta))
                    if policy.action == GoalReviewAction.REPRIORITIZE:
                        priority += policy.priority_delta
                    category = (policy.target_category
                                if policy.action == GoalReviewAction.REFRAME
                                else goal.category)
                    proposals.append(GoalReviewProposal(
                        event_id=event.event_id,
                        owner_id=goal.owner_id,
                        goal_id=goal.goal_id,
                        policy_id=policy.policy_id,
                        action=policy.action,
                        current_category=goal.category,
                        proposed_category=category,
                        current_priority=goal.priority,
                        proposed_priority=priority,
                        current_confidence=goal.confidence,
                        proposed_confidence=confidence,
                        reason=f"matched event {event.event_type!r}",
                    ))
        return tuple(sorted(proposals, key=lambda item: (
            item.event_id, item.owner_id, item.goal_id, item.policy_id
        )))
