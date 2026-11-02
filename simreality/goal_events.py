"""Explicitly map authoritative world events to NPC goal progress."""
from dataclasses import dataclass
from typing import Iterable
from .goals import GoalBook, GoalStatus
from .world_events import WorldEvent

@dataclass(frozen=True)
class GoalProgressPolicy:
    policy_id: str
    event_type: str
    goal_category: str
    progress_delta: float
    required_attributes: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        for value in (self.policy_id, self.event_type, self.goal_category):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("policy identifiers must be non-empty")
        if isinstance(self.progress_delta, bool) or not isinstance(self.progress_delta, (int, float)) or not 0 < self.progress_delta <= 1:
            raise ValueError("progress_delta must be greater than 0 and at most 1")
        if len(set(self.required_attributes)) != len(self.required_attributes):
            raise ValueError("required attributes must be unique")
        if any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in self.required_attributes):
            raise ValueError("required attributes must be string pairs")

@dataclass(frozen=True)
class GoalProgressUpdate:
    event_id: str
    goal_id: str
    previous_progress: float
    progress: float
    policy_id: str

class GoalEventAdapter:
    """Apply configured event evidence to active goals; never infer intent."""
    def __init__(self, goals: GoalBook, policies: Iterable[GoalProgressPolicy]):
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        items = tuple(policies)
        if any(not isinstance(p, GoalProgressPolicy) for p in items):
            raise TypeError("policies must contain GoalProgressPolicy values")
        if len({p.policy_id for p in items}) != len(items):
            raise ValueError("policy IDs must be unique")
        self.goals = goals
        self.policies = tuple(sorted(items, key=lambda p: p.policy_id))
        self._processed = {}

    @staticmethod
    def _signature(event):
        return (event.tick, event.event_type, tuple(event.participants),
                tuple(event.witnesses), repr(event.attributes))

    def apply(self, events: Iterable[WorldEvent]):
        items = tuple(events)
        if any(not isinstance(e, WorldEvent) for e in items):
            raise TypeError("events must contain WorldEvent values")
        if len({e.event_id for e in items}) != len(items):
            raise ValueError("event IDs must be unique within a batch")
        pending = []
        for event in sorted(items, key=lambda e: (e.tick, e.event_id)):
            signature = self._signature(event)
            previous = self._processed.get(event.event_id)
            if previous is not None:
                if previous != signature:
                    raise ValueError(f"event ID {event.event_id!r} was reused with different content")
                continue
            pending.append((event, signature))
        updates = []
        for event, signature in pending:
            attrs = dict(event.attributes)
            owners = set(event.participants)
            for policy in self.policies:
                if event.event_type != policy.event_type:
                    continue
                if any(attrs.get(k) != v for k, v in policy.required_attributes):
                    continue
                for goal in sorted(self.goals.goals.values(), key=lambda g: g.goal_id):
                    if goal.owner_id not in owners or goal.category != policy.goal_category or goal.status != GoalStatus.ACTIVE:
                        continue
                    old = goal.progress
                    new = min(1.0, old + policy.progress_delta)
                    self.goals.update_progress(goal.goal_id, new)
                    updates.append(GoalProgressUpdate(event.event_id, goal.goal_id, old, new, policy.policy_id))
            self._processed[event.event_id] = signature
        return tuple(updates)

    def processed_event_ids(self):
        return tuple(sorted(self._processed))
