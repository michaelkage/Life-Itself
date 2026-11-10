"""Authoritative NPC physical-presence state derived from explicit world locations and travel.

Locations are symbolic world-node IDs. In-transit presence retains the exact
road edge and fractional edge progress; this module does not invent coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable

from .travel import TravelLedger
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class NPCPresence:
    owner_id: str
    status: str
    location_id: str | None
    journey_id: str | None
    edge_id: str | None
    edge_progress: float
    updated_tick: int

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if self.status not in ("at_location", "travelling", "blocked", "unreachable"):
            raise ValueError("invalid presence status")
        if self.location_id is not None and (not isinstance(self.location_id, str) or not self.location_id.strip()):
            raise ValueError("location_id must be None or a non-empty string")
        if self.journey_id is not None and (not isinstance(self.journey_id, str) or not self.journey_id.strip()):
            raise ValueError("journey_id must be None or a non-empty string")
        if self.edge_id is not None and (not isinstance(self.edge_id, str) or not self.edge_id.strip()):
            raise ValueError("edge_id must be None or a non-empty string")
        if isinstance(self.edge_progress, bool) or not isinstance(self.edge_progress, (int, float)) or not math.isfinite(self.edge_progress) or self.edge_progress < 0:
            raise ValueError("edge_progress must be finite and non-negative")
        if isinstance(self.updated_tick, bool) or not isinstance(self.updated_tick, int) or self.updated_tick < 0:
            raise ValueError("updated_tick must be a non-negative integer")
        if self.status == "at_location":
            if self.location_id is None or self.edge_id is not None or self.edge_progress != 0:
                raise ValueError("at-location presence requires a location and no active edge")
        else:
            if self.journey_id is None or self.location_id is None:
                raise ValueError("in-transit presence requires a journey and current node")
            if self.edge_id is None and self.edge_progress != 0:
                raise ValueError("edge progress requires an edge ID")


class PresenceLedger:
    """Owner-scoped, queryable current location and road-edge presence."""

    def __init__(self, records: Iterable[NPCPresence] = ()):
        self._records: dict[str, NPCPresence] = {}
        self._ticks: dict[int, tuple[str, tuple[NPCPresence, ...]]] = {}
        for record in records:
            if not isinstance(record, NPCPresence):
                raise TypeError("records must contain NPCPresence values")
            self._records[record.owner_id] = record

    def get(self, owner_id: str) -> NPCPresence | None:
        return self._records.get(owner_id)

    def snapshot(self) -> tuple[NPCPresence, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def occupants(self, location_id: str) -> tuple[str, ...]:
        if not isinstance(location_id, str) or not location_id.strip():
            raise ValueError("location_id must be a non-empty string")
        return tuple(sorted(record.owner_id for record in self._records.values()
                            if record.status == "at_location" and record.location_id == location_id))

    def place(self, owner_id: str, location_id: str, tick: int) -> NPCPresence:
        if not isinstance(owner_id, str) or not owner_id.strip() or not isinstance(location_id, str) or not location_id.strip():
            raise ValueError("owner_id and location_id must be non-empty strings")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        previous = self._records.get(owner_id)
        if previous is not None and previous.status != "at_location":
            raise ValueError("cannot relocate an NPC while a journey is active")
        if previous is not None and previous.location_id != location_id:
            raise ValueError("existing NPCs must move through an explicit travel journey")
        if previous is not None and tick < previous.updated_tick:
            raise ValueError("presence updates must be monotonic")
        last_journey_id = previous.journey_id if previous is not None else None
        record = NPCPresence(owner_id, "at_location", location_id, last_journey_id, None, 0.0, tick)
        self._records[owner_id] = record
        return record

    def _sync(self, tick: int, signature: str, records: tuple[NPCPresence, ...]) -> tuple[NPCPresence, ...]:
        prior = self._ticks.get(tick)
        if prior is not None:
            if prior[0] != signature:
                raise ValueError(f"conflicting presence tick replay: {tick}")
            return prior[1]
        if self._ticks and tick <= max(self._ticks):
            raise ValueError("new presence ticks must advance monotonically")
        for record in records:
            self._records[record.owner_id] = record
        self._ticks[tick] = (signature, records)
        return records

    def tick_snapshot(self):
        return tuple((tick, signature, records) for tick, (signature, records) in sorted(self._ticks.items()))

    def _restore_tick(self, tick, signature, records):
        if tick in self._ticks:
            raise ValueError(f"duplicate presence tick: {tick}")
        self._ticks[tick] = (signature, records)


class PresenceTickAdapter:
    """Synchronize current NPC presence from the authoritative travel ledger."""

    def __init__(self, ledger: PresenceLedger):
        if not isinstance(ledger, PresenceLedger):
            raise TypeError("ledger must be a PresenceLedger")
        self.ledger = ledger

    def synchronize(self, tick: int, travel: TravelLedger, *, events: WorldEventLedger | None = None) -> tuple[NPCPresence, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(travel, TravelLedger):
            raise TypeError("travel must be a TravelLedger")
        if events is not None and not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger or None")
        journeys = travel.snapshot()
        signature = json.dumps([
            (j.journey_id, j.owner_id, j.status, j.path, j.edge_ids, j.edge_index,
             j.edge_progress, j.destination, j.arrived_tick)
            for j in journeys
        ], sort_keys=True, separators=(",", ":"), allow_nan=False)
        if tick in self.ledger._ticks:
            if self.ledger._ticks[tick][0] != signature:
                raise ValueError(f"conflicting presence tick replay: {tick}")
            if events is not None:
                self._emit(tick, self.ledger._ticks[tick][1], events)
            return self.ledger._ticks[tick][1]

        latest_by_owner = {}
        for journey in journeys:
            previous_journey = latest_by_owner.get(journey.owner_id)
            if previous_journey is None or (journey.started_tick, journey.journey_id) > (previous_journey.started_tick, previous_journey.journey_id):
                latest_by_owner[journey.owner_id] = journey
        updates = []
        for journey in sorted(latest_by_owner.values(), key=lambda item: item.owner_id):
            if journey.status == "arrived":
                record = NPCPresence(journey.owner_id, "at_location", journey.destination,
                                     journey.journey_id, None, 0.0, tick)
            elif journey.status in ("travelling", "blocked", "unreachable"):
                edge_id = journey.edge_ids[journey.edge_index] if journey.edge_index < len(journey.edge_ids) else None
                record = NPCPresence(journey.owner_id, journey.status, journey.path[journey.edge_index],
                                     journey.journey_id, edge_id, journey.edge_progress, tick)
            else:
                continue
            previous = self.ledger.get(journey.owner_id)
            if previous is not None:
                if previous.updated_tick > tick:
                    raise ValueError(f"journey would rewind recorded NPC presence: {journey.owner_id}")
                if previous.status != "at_location" and previous.journey_id != journey.journey_id:
                    raise ValueError(f"NPC already has presence on another journey: {journey.owner_id}")
                if previous.status == "at_location":
                    if previous.journey_id == journey.journey_id:
                        if journey.status != "arrived":
                            raise ValueError(f"arrived journey conflicts with active travel state: {journey.owner_id}")
                    elif previous.updated_tick > journey.started_tick:
                        raise ValueError(f"journey predates the latest recorded NPC presence: {journey.owner_id}")
                    elif previous.location_id != journey.origin:
                        raise ValueError(f"journey origin conflicts with recorded NPC presence: {journey.owner_id}")
            updates.append(record)
        result = self.ledger._sync(tick, signature, tuple(sorted(updates, key=lambda item: item.owner_id)))
        if events is not None:
            self._emit(tick, result, events)
        return result

    @staticmethod
    def _emit(tick: int, records: tuple[NPCPresence, ...], events: WorldEventLedger):
        for record in records:
            events.append(WorldEventLedger.make_event(
                f"presence:{tick}:{record.owner_id}", tick, "npc_presence_updated",
                participants=(record.owner_id,),
                attributes={"status": record.status, "location_id": record.location_id,
                            "journey_id": record.journey_id, "edge_id": record.edge_id,
                            "edge_progress": record.edge_progress},
            ))
