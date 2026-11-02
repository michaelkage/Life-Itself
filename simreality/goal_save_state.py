"""Canonical persistence for deterministic NPC goal books."""
from __future__ import annotations
from dataclasses import dataclass
import json
from .goals import GoalBook, GoalStatus, NPCGoal

@dataclass(frozen=True)
class GoalBookSnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.records, tuple):
            raise ValueError("records must be a tuple")
        ids = []
        for record in self.records:
            if not isinstance(record, tuple) or len(record) != 13:
                raise ValueError("invalid goal record")
            ids.append(record[0])
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("goal records must have unique sorted IDs")

    @classmethod
    def capture(cls, book: GoalBook):
        if not isinstance(book, GoalBook):
            raise TypeError("book must be a GoalBook")
        return cls(book.snapshot())

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "records": [list(r) for r in self.records]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal snapshot schema version")
            records = []
            for item in raw["records"]:
                if not isinstance(item, list) or len(item) != 13:
                    raise ValueError("invalid goal record")
                records.append((
                    item[0], item[1], item[2], item[3], item[4], item[5], item[6],
                    item[7], item[8], tuple(item[9]), tuple(item[10]), item[11],
                    tuple(tuple(pair) for pair in item[12]),
                ))
            result = cls(tuple(records))
            if result.to_json() != payload:
                raise ValueError("goal snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal snapshot") from exc

    def restore(self):
        book = GoalBook()
        for r in self.records:
            goal = NPCGoal(
                r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8],
                tuple(r[9]), tuple(r[10]), GoalStatus(r[11]), dict(r[12]),
            )
            book.add(goal)
        return book
