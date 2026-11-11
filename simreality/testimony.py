"""Persistent, decaying testimony derived from witness recall records."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .witness_recall import WitnessRecall


@dataclass(frozen=True)
class TestimonyDetail:
    detail_id: str
    attribute_key: str
    value: str | int | float | bool | None
    initial_confidence: float


@dataclass(frozen=True)
class TestimonyRecord:
    testimony_id: str
    event_id: str
    witness_id: str
    event_tick: int
    recorded_hour: float
    decay_rate_per_hour: float
    details: tuple[TestimonyDetail, ...]
    omitted_detail_ids: tuple[str, ...]

    def confidence_at(self, detail: TestimonyDetail, current_hour: float) -> float:
        if isinstance(current_hour, bool) or not isinstance(current_hour, (int, float)) or not math.isfinite(current_hour) or current_hour < self.recorded_hour:
            raise ValueError("current_hour must be finite and >= recorded_hour")
        return detail.initial_confidence * math.exp(-self.decay_rate_per_hour * (current_hour - self.recorded_hour))


class TestimonyLedger:
    """Append-only witness account ledger with replay-safe IDs and canonical JSON."""

    SCHEMA_VERSION = 1

    def __init__(self, records: tuple[TestimonyRecord, ...] = ()) -> None:
        self._records: dict[str, TestimonyRecord] = {}
        for record in records:
            self.append(record)

    @staticmethod
    def from_recall(
        testimony_id: str,
        recall: WitnessRecall,
        recorded_hour: float,
        *,
        decay_rate_per_hour: float = 0.01,
    ) -> TestimonyRecord:
        if not isinstance(testimony_id, str) or not testimony_id.strip():
            raise ValueError("testimony_id must be non-empty")
        for name, value in (("recorded_hour", recorded_hour), ("decay_rate_per_hour", decay_rate_per_hour)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if recorded_hour < 0 or decay_rate_per_hour < 0:
            raise ValueError("recorded_hour and decay rate must be non-negative")
        details = tuple(TestimonyDetail(d.detail_id, d.attribute_key, d.value, d.confidence) for d in recall.details)
        return TestimonyRecord(testimony_id, recall.event_id, recall.witness_id, recall.event_tick,
                               float(recorded_hour), float(decay_rate_per_hour), details, recall.omitted_detail_ids)

    def append(self, record: TestimonyRecord) -> TestimonyRecord:
        if not isinstance(record, TestimonyRecord):
            raise TypeError("record must be TestimonyRecord")
        if not record.testimony_id or not record.event_id or not record.witness_id:
            raise ValueError("testimony, event, and witness IDs must be non-empty")
        if record.recorded_hour < 0 or record.decay_rate_per_hour < 0 or not math.isfinite(record.recorded_hour + record.decay_rate_per_hour):
            raise ValueError("recorded hour and decay rate must be finite and non-negative")
        existing = self._records.get(record.testimony_id)
        if existing is not None and existing != record:
            raise ValueError("testimony ID reused with different content")
        self._records.setdefault(record.testimony_id, record)
        return self._records[record.testimony_id]

    def get(self, testimony_id: str) -> TestimonyRecord:
        return self._records[testimony_id]

    def snapshot(self) -> tuple[TestimonyRecord, ...]:
        return tuple(self._records[key] for key in sorted(self._records))

    def to_json(self) -> str:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "records": [{
                "testimony_id": r.testimony_id, "event_id": r.event_id,
                "witness_id": r.witness_id, "event_tick": r.event_tick,
                "recorded_hour": r.recorded_hour, "decay_rate_per_hour": r.decay_rate_per_hour,
                "details": [{"detail_id": d.detail_id, "attribute_key": d.attribute_key,
                             "value": d.value, "initial_confidence": d.initial_confidence} for d in r.details],
                "omitted_detail_ids": list(r.omitted_detail_ids),
            } for r in self.snapshot()],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "TestimonyLedger":
        try:
            raw = json.loads(payload)
            if raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported testimony schema")
            records = []
            for r in raw["records"]:
                details = tuple(TestimonyDetail(d["detail_id"], d["attribute_key"], d["value"], d["initial_confidence"]) for d in r["details"])
                records.append(TestimonyRecord(r["testimony_id"], r["event_id"], r["witness_id"], r["event_tick"],
                    r["recorded_hour"], r["decay_rate_per_hour"], details, tuple(r["omitted_detail_ids"])))
            return cls(tuple(records))
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid testimony snapshot") from exc
