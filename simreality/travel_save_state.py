from __future__ import annotations

"""Canonical JSON persistence for in-progress NPC journeys and tick replay."""
import json
from dataclasses import dataclass
from .travel import TravelJourney, TravelLedger, TravelTickResult


def _journey_payload(j):
    return {"journey_id": j.journey_id, "owner_id": j.owner_id, "origin": j.origin,
            "destination": j.destination, "path": list(j.path), "edge_ids": list(j.edge_ids),
            "edge_index": j.edge_index, "edge_progress": j.edge_progress,
            "elapsed_cost": j.elapsed_cost, "status": j.status,
            "started_tick": j.started_tick, "arrived_tick": j.arrived_tick}


def _read_journey(item):
    return TravelJourney(item["journey_id"], item["owner_id"], item["origin"], item["destination"],
                         tuple(item["path"]), tuple(item["edge_ids"]), item["edge_index"],
                         item["edge_progress"], item["elapsed_cost"], item["status"],
                         item["started_tick"], item.get("arrived_tick"))


def _result_payload(result):
    return {"tick": result.tick, "journeys": [_journey_payload(j) for j in result.journeys],
            "arrivals": list(result.arrivals), "blocked": list(result.blocked)}


def _read_result(item):
    return TravelTickResult(item["tick"], tuple(_read_journey(j) for j in item["journeys"]),
                            tuple(item["arrivals"]), tuple(item["blocked"]))


@dataclass(frozen=True)
class TravelSnapshot:
    journeys: tuple[TravelJourney, ...]
    ticks: tuple[tuple[int, str, TravelTickResult], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.journeys, tuple) or any(not isinstance(j, TravelJourney) for j in self.journeys):
            raise ValueError("journeys must be a tuple of TravelJourney values")
        ids = [j.journey_id for j in self.journeys]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("journeys must have unique canonical IDs")
        if not isinstance(self.ticks, tuple):
            raise ValueError("ticks must be a tuple")
        tick_ids = [item[0] for item in self.ticks]
        if tick_ids != sorted(tick_ids) or len(tick_ids) != len(set(tick_ids)):
            raise ValueError("travel ticks must have unique increasing IDs")
        for tick, signature, result in self.ticks:
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0 or not isinstance(signature, str) or not signature:
                raise ValueError("invalid travel tick history entry")
            if not isinstance(result, TravelTickResult) or result.tick != tick:
                raise ValueError("travel tick result does not match its history key")

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, TravelLedger):
            raise TypeError("ledger must be a TravelLedger")
        return cls(ledger.snapshot(), ledger.tick_snapshot())

    def to_json(self):
        payload = {"schema_version": self.SCHEMA_VERSION,
                   "journeys": [_journey_payload(j) for j in self.journeys],
                   "ticks": [{"tick": tick, "signature": signature, "result": _result_payload(result)}
                             for tick, signature, result in self.ticks]}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported travel snapshot schema version")
            journeys = tuple(_read_journey(j) for j in raw["journeys"])
            ticks = tuple((item["tick"], item["signature"], _read_result(item["result"]))
                          for item in raw["ticks"])
            snapshot = cls(journeys, ticks)
            if snapshot.to_json() != payload:
                raise ValueError("travel snapshot must use canonical JSON")
            return snapshot
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid travel snapshot") from exc

    def restore(self):
        ledger = TravelLedger(self.journeys)
        for tick, signature, result in self.ticks:
            ledger._restore_tick(tick, signature, result)
        return ledger
