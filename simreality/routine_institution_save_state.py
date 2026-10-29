"""Canonical JSON persistence for institutional routine records."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .routine_institution_ledger import InstitutionalRecord, RoutineInstitutionLedger


@dataclass(frozen=True)
class RoutineInstitutionSnapshot:
    records: tuple[InstitutionalRecord, ...]
    processed_signatures: tuple[tuple[str, tuple[tuple[str, object], ...]], ...]

    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger: RoutineInstitutionLedger) -> "RoutineInstitutionSnapshot":
        if not isinstance(ledger, RoutineInstitutionLedger):
            raise TypeError("ledger must be a RoutineInstitutionLedger")
        return cls(ledger.snapshot(), tuple(
            (event_id, ledger._processed[event_id])
            for event_id in sorted(ledger._processed)
        ))

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(r, InstitutionalRecord) for r in self.records):
            raise ValueError("records must be a tuple of InstitutionalRecord values")
        keys = [(r.institution_id, r.person_id) for r in self.records]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("institutional records must be uniquely sorted")
        for record in self.records:
            for name in ("institution_id", "person_id"):
                value = getattr(record, name)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{name} must be non-empty")
            for name in ("late_arrivals", "missed_appointments", "total_delay_minutes", "last_event_tick"):
                value = getattr(record, name)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError(f"{name} must be a non-negative integer")
        ids = [item[0] for item in self.processed_signatures]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("processed event signatures must be uniquely sorted")
        if any(not isinstance(event_id, str) or not event_id.strip() for event_id in ids):
            raise ValueError("processed event IDs must be non-empty")

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "records": [asdict(r) for r in self.records],
            "processed_signatures": [
                {"event_id": event_id, "signature": [list(pair) for pair in signature]}
                for event_id, signature in self.processed_signatures
            ],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "RoutineInstitutionSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported routine institution snapshot schema")
            records = tuple(InstitutionalRecord(**item) for item in raw["records"])
            signatures = tuple(
                (item["event_id"], tuple((pair[0], pair[1]) for pair in item["signature"]))
                for item in raw["processed_signatures"]
            )
            return cls(records, signatures)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid routine institution snapshot") from exc

    def restore(self) -> RoutineInstitutionLedger:
        ledger = RoutineInstitutionLedger()
        ledger._records = {(r.institution_id, r.person_id): r for r in self.records}
        ledger._processed = {event_id: signature for event_id, signature in self.processed_signatures}
        return ledger
