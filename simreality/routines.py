"""Persistent NPC routines with explicit, replayable disruption inputs.

This module proposes where a person intended to be, then resolves the current
period against current conditions. It never assumes the routine must succeed.
Any uncertainty is resolved from a caller-supplied sample so save/replay can
reproduce the exact outcome without making the world perfectly predictable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable


class DisruptionKind(str, Enum):
    TRAFFIC = "traffic"
    WEATHER = "weather"
    ALARM_FAILURE = "alarm_failure"
    LOW_MOTIVATION = "low_motivation"
    UNEXPECTED_EVENT = "unexpected_event"
    LOCATION_AVOIDANCE = "location_avoidance"
    ILLNESS = "illness"
    SOCIAL_OBLIGATION = "social_obligation"


class RoutineOutcome(str, Enum):
    ON_TIME = "on_time"
    DELAYED = "delayed"
    REDIRECTED = "redirected"
    MISSED = "missed"


@dataclass(frozen=True)
class RoutineBlock:
    routine_id: str
    owner_id: str
    activity: str
    location_id: str
    start_minute: int
    end_minute: int
    priority: float = 0.5
    flexibility_minutes: int = 15
    fallback_activity: str | None = None
    fallback_location_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("routine_id", "owner_id", "activity", "location_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.start_minute, bool) or isinstance(self.end_minute, bool):
            raise ValueError("routine times must be integers")
        if not isinstance(self.start_minute, int) or not isinstance(self.end_minute, int):
            raise ValueError("routine times must be integers")
        if not (0 <= self.start_minute < self.end_minute <= 1440):
            raise ValueError("routine block must fit within one day and have positive duration")
        if not math.isfinite(self.priority) or not 0.0 <= self.priority <= 1.0:
            raise ValueError("priority must be finite and between 0 and 1")
        if isinstance(self.flexibility_minutes, bool) or not isinstance(self.flexibility_minutes, int) or self.flexibility_minutes < 0:
            raise ValueError("flexibility_minutes must be a non-negative integer")
        for name in ("fallback_activity", "fallback_location_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")


@dataclass(frozen=True)
class RoutineDisruption:
    disruption_id: str
    owner_id: str
    kind: DisruptionKind
    severity: float
    start_minute: int
    end_minute: int
    affected_location_id: str | None = None
    delay_minutes: int = 0
    alternative_activity: str | None = None
    alternative_location_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.disruption_id, str) or not self.disruption_id.strip():
            raise ValueError("disruption_id must be a non-empty string")
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(self.kind, DisruptionKind):
            raise ValueError("kind must be a DisruptionKind")
        if not math.isfinite(self.severity) or not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be finite and between 0 and 1")
        if isinstance(self.start_minute, bool) or isinstance(self.end_minute, bool) or not isinstance(self.start_minute, int) or not isinstance(self.end_minute, int) or not 0 <= self.start_minute < self.end_minute <= 1440:
            raise ValueError("disruption window must fit within one day and have positive duration")
        if isinstance(self.delay_minutes, bool) or not isinstance(self.delay_minutes, int) or self.delay_minutes < 0:
            raise ValueError("delay_minutes must be a non-negative integer")
        for name in ("affected_location_id", "alternative_activity", "alternative_location_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be None or a non-empty string")


@dataclass(frozen=True)
class RoutineResolution:
    routine_id: str
    owner_id: str
    intended_activity: str
    intended_location_id: str
    actual_activity: str
    actual_location_id: str | None
    outcome: RoutineOutcome
    delay_minutes: int
    disruption_ids: tuple[str, ...]
    reason: str


class RoutineBook:
    """Store recurring routine blocks and resolve one period against disruptions."""

    def __init__(self, blocks: Iterable[RoutineBlock] = ()) -> None:
        self._blocks: dict[str, RoutineBlock] = {}
        for block in blocks:
            self.add(block)

    def add(self, block: RoutineBlock) -> None:
        if not isinstance(block, RoutineBlock):
            raise TypeError("block must be a RoutineBlock")
        if block.routine_id in self._blocks:
            raise ValueError(f"duplicate routine ID: {block.routine_id}")
        overlaps = [
            other.routine_id for other in self._blocks.values()
            if other.owner_id == block.owner_id
            and max(other.start_minute, block.start_minute) < min(other.end_minute, block.end_minute)
        ]
        if overlaps:
            raise ValueError(f"routine block overlaps existing block: {sorted(overlaps)[0]}")
        self._blocks[block.routine_id] = block

    def for_period(self, owner_id: str, minute_of_day: int) -> tuple[RoutineBlock, ...]:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        return tuple(sorted(
            (b for b in self._blocks.values()
             if b.owner_id == owner_id and b.start_minute <= minute_of_day < b.end_minute),
            key=lambda b: b.routine_id,
        ))

    def resolve(
        self,
        block: RoutineBlock,
        minute_of_day: int,
        disruptions: Iterable[RoutineDisruption] = (),
        *,
        outcome_sample: float = 0.0,
    ) -> RoutineResolution:
        if block.routine_id not in self._blocks or self._blocks[block.routine_id] != block:
            raise ValueError("block must be registered in this RoutineBook")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        if not math.isfinite(outcome_sample) or not 0.0 <= outcome_sample <= 1.0:
            raise ValueError("outcome_sample must be finite and between 0 and 1")
        candidates = tuple(sorted(disruptions, key=lambda d: d.disruption_id))
        if any(not isinstance(d, RoutineDisruption) for d in candidates):
            raise TypeError("disruptions must contain RoutineDisruption values")
        relevant = tuple(
            d for d in candidates
            if d.owner_id == block.owner_id
            and d.start_minute <= minute_of_day < d.end_minute
            and (d.affected_location_id is None or d.affected_location_id == block.location_id)
        )
        ids = tuple(d.disruption_id for d in relevant)
        matched = next((d for d in relevant if outcome_sample < d.severity), None)
        if matched is None:
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                block.activity, block.location_id, RoutineOutcome.ON_TIME, 0, ids,
                "routine proceeds; no applicable disruption crossed the supplied outcome sample",
            )
        if matched.alternative_activity or matched.alternative_location_id:
            activity = matched.alternative_activity or block.fallback_activity or block.activity
            location = matched.alternative_location_id or block.fallback_location_id or block.location_id
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                activity, location, RoutineOutcome.REDIRECTED, 0, ids,
                f"redirected by {matched.kind.value}: {matched.disruption_id}",
            )
        delay = matched.delay_minutes
        if matched.kind is DisruptionKind.ALARM_FAILURE:
            delay = max(delay, 30)
        if matched.kind is DisruptionKind.LOW_MOTIVATION:
            delay = max(delay, 15)
        if delay <= block.flexibility_minutes:
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                block.activity, block.location_id, RoutineOutcome.DELAYED, delay, ids,
                f"delayed by {matched.kind.value}: within routine flexibility",
            )
        if block.fallback_activity or block.fallback_location_id:
            return RoutineResolution(
                block.routine_id, block.owner_id, block.activity, block.location_id,
                block.fallback_activity or block.activity,
                block.fallback_location_id or block.location_id,
                RoutineOutcome.REDIRECTED, delay, ids,
                f"fallback selected after {matched.kind.value}: {matched.disruption_id}",
            )
        return RoutineResolution(
            block.routine_id, block.owner_id, block.activity, block.location_id,
            block.activity, None, RoutineOutcome.MISSED, delay, ids,
            f"routine missed after {matched.kind.value}: delay exceeds flexibility",
        )

    def snapshot(self) -> tuple[RoutineBlock, ...]:
        return tuple(sorted(self._blocks.values(), key=lambda b: b.routine_id))
