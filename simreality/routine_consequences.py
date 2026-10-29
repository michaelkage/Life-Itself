"""Apply explicit, location-owned policies to recorded routine outcomes.

A routine outcome is a fact; consequences depend on an explicit policy. This
adapter never assumes every late employee is punished or every missed
appointment has the same result. Only configured activity/location policies emit
consequence events.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .world_events import WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class RoutineImpactPolicy:
    """A transparent consequence rule for one activity at one location."""
    policy_id: str
    activity: str
    location_id: str
    delay_tolerance_minutes: int = 0
    delay_event_type: str | None = None
    missed_event_type: str | None = None

    def __post_init__(self) -> None:
        for name in ("policy_id", "activity", "location_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.delay_tolerance_minutes, bool) or not isinstance(self.delay_tolerance_minutes, int) or self.delay_tolerance_minutes < 0:
            raise ValueError("delay_tolerance_minutes must be a non-negative integer")
        for name in ("delay_event_type", "missed_event_type"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")


class RoutineConsequenceAdapter:
    """Turn eligible routine facts into explicit policy consequence events."""

    def __init__(self, events: WorldEventLedger, policies: Iterable[RoutineImpactPolicy]) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        items = tuple(policies)
        if any(not isinstance(item, RoutineImpactPolicy) for item in items):
            raise TypeError("policies must contain RoutineImpactPolicy values")
        keys = [(p.activity, p.location_id) for p in items]
        if len(keys) != len(set(keys)):
            raise ValueError("only one impact policy may exist per activity/location pair")
        self.events = events
        self._policies = {(p.activity, p.location_id): p for p in items}

    def apply(self, routine_event_ids: Iterable[str]) -> tuple[WorldEvent, ...]:
        """Evaluate routine events in stable order and append configured effects.

        The routine event must already exist in the shared ledger. Consequence
        IDs derive from the source event and policy, making identical retries
        idempotent.
        """
        ids = tuple(routine_event_ids)
        if any(not isinstance(event_id, str) or not event_id.strip() for event_id in ids):
            raise ValueError("routine_event_ids must contain non-empty strings")
        if len(ids) != len(set(ids)):
            raise ValueError("routine_event_ids must be unique")
        generated = []
        for event_id in sorted(ids):
            source = self.events.get(event_id)
            if source.event_type != "routine_execution":
                raise ValueError(f"event is not a routine execution: {event_id}")
            attrs = dict(source.attributes)
            activity = attrs.get("intended_activity")
            location = attrs.get("intended_location_id")
            if not isinstance(activity, str) or not isinstance(location, str):
                raise ValueError(f"routine event lacks intended activity/location: {event_id}")
            policy = self._policies.get((activity, location))
            if policy is None:
                continue
            outcome = attrs.get("outcome")
            delay = attrs.get("delay_minutes", 0)
            if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
                raise ValueError(f"routine event has invalid delay_minutes: {event_id}")
            consequence_type = None
            if outcome == "missed" and policy.missed_event_type is not None:
                consequence_type = policy.missed_event_type
            elif outcome == "delayed" and delay > policy.delay_tolerance_minutes and policy.delay_event_type is not None:
                consequence_type = policy.delay_event_type
            if consequence_type is None:
                continue
            owner = source.participants[0] if source.participants else None
            generated.append(WorldEventLedger.make_event(
                f"routine-consequence:{source.event_id}:{policy.policy_id}",
                source.tick,
                consequence_type,
                participants=(owner,) if owner else (),
                attributes={
                    "source_event_id": source.event_id,
                    "policy_id": policy.policy_id,
                    "activity": activity,
                    "location_id": location,
                    "outcome": str(outcome),
                    "delay_minutes": delay,
                },
            ))
        return self.events.append_many(generated)
