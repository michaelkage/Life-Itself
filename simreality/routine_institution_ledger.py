"""Persistent, replayable institutional records derived from consequence events.

This ledger is deliberately narrower than an employer or clinic simulation. It
tracks only explicit events supplied to it; it does not decide who deserves
punishment, infer absences, or create employment/medical outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .world_events import WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class InstitutionalRecord:
    institution_id: str
    person_id: str
    late_arrivals: int = 0
    missed_appointments: int = 0
    total_delay_minutes: int = 0
    last_event_tick: int = 0


class RoutineInstitutionLedger:
    """Accumulate explicit workplace/appointment consequence events."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], InstitutionalRecord] = {}
        self._processed: dict[str, tuple[tuple[str, object], ...]] = {}

    @staticmethod
    def _signature(event: WorldEvent) -> tuple[tuple[str, object], ...]:
        return (
            ("event_id", event.event_id),
            ("tick", event.tick),
            ("event_type", event.event_type),
            ("participants", ",".join(event.participants)),
            ("attributes", repr(event.attributes)),
        )

    def apply(self, events: Iterable[WorldEvent]) -> tuple[InstitutionalRecord, ...]:
        items = tuple(events)
        if any(not isinstance(event, WorldEvent) for event in items):
            raise TypeError("events must contain WorldEvent values")
        if len({event.event_id for event in items}) != len(items):
            raise ValueError("event IDs must be unique within a batch")

        # Validate the complete batch before mutating state.
        pending = []
        for event in sorted(items, key=lambda item: (item.tick, item.event_id)):
            signature = self._signature(event)
            previous = self._processed.get(event.event_id)
            if previous is not None:
                if previous != signature:
                    raise ValueError(f"event ID {event.event_id!r} was reused with different content")
                continue
            if event.event_type not in {"workplace_late_arrival", "appointment_missed"}:
                continue
            attrs = dict(event.attributes)
            institution_id = attrs.get("location_id")
            if not isinstance(institution_id, str) or not institution_id.strip():
                raise ValueError("institution consequence requires location_id")
            if len(event.participants) != 1:
                raise ValueError("institution consequence must identify exactly one person")
            person_id = event.participants[0]
            delay = attrs.get("delay_minutes", 0)
            if isinstance(delay, bool) or not isinstance(delay, int) or delay < 0:
                raise ValueError("delay_minutes must be a non-negative integer")
            pending.append((event, signature, institution_id, person_id, delay))

        changed: set[tuple[str, str]] = set()
        for event, signature, institution_id, person_id, delay in pending:
            key = (institution_id, person_id)
            old = self._records.get(key, InstitutionalRecord(institution_id, person_id))
            if event.event_type == "workplace_late_arrival":
                updated = InstitutionalRecord(
                    institution_id, person_id, old.late_arrivals + 1,
                    old.missed_appointments, old.total_delay_minutes + delay,
                    max(old.last_event_tick, event.tick),
                )
            else:
                updated = InstitutionalRecord(
                    institution_id, person_id, old.late_arrivals,
                    old.missed_appointments + 1, old.total_delay_minutes,
                    max(old.last_event_tick, event.tick),
                )
            self._records[key] = updated
            self._processed[event.event_id] = signature
            changed.add(key)
        return tuple(self._records[key] for key in sorted(changed))

    def get(self, institution_id: str, person_id: str) -> InstitutionalRecord:
        return self._records.get(
            (institution_id, person_id),
            InstitutionalRecord(institution_id, person_id),
        )

    def snapshot(self) -> tuple[InstitutionalRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def processed_event_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._processed))
