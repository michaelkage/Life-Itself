"""Canonical persistence for planned NPC routine blocks."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .routines import RoutineBook, RoutineBlock


def _block_payload(block: RoutineBlock) -> dict:
    return {
        "routine_id": block.routine_id,
        "owner_id": block.owner_id,
        "activity": block.activity,
        "location_id": block.location_id,
        "start_minute": block.start_minute,
        "end_minute": block.end_minute,
        "priority": block.priority,
        "flexibility_minutes": block.flexibility_minutes,
        "fallback_activity": block.fallback_activity,
        "fallback_location_id": block.fallback_location_id,
    }


@dataclass(frozen=True)
class RoutineBookSnapshot:
    """Versioned, canonical snapshot of intended NPC schedules.

    This persists schedule definitions, not generated disruptions or resolved
    attendance. Those are explicit simulation inputs/results and will be
    persisted when the routine execution ledger is integrated with world ticks.
    """
    blocks: tuple[RoutineBlock, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.blocks, tuple):
            raise ValueError("blocks must be a tuple")
        book = RoutineBook(self.blocks)
        if book.snapshot() != self.blocks:
            raise ValueError("routine blocks must be in canonical order")

    @classmethod
    def capture(cls, book: RoutineBook) -> "RoutineBookSnapshot":
        if not isinstance(book, RoutineBook):
            raise TypeError("book must be a RoutineBook")
        return cls(book.snapshot())

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "blocks": [_block_payload(block) for block in self.blocks],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "RoutineBookSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported routine snapshot schema version")
            blocks = tuple(RoutineBlock(
                routine_id=item["routine_id"],
                owner_id=item["owner_id"],
                activity=item["activity"],
                location_id=item["location_id"],
                start_minute=item["start_minute"],
                end_minute=item["end_minute"],
                priority=item.get("priority", 0.5),
                flexibility_minutes=item.get("flexibility_minutes", 15),
                fallback_activity=item.get("fallback_activity"),
                fallback_location_id=item.get("fallback_location_id"),
            ) for item in raw["blocks"])
            return cls(blocks)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid routine book snapshot") from exc

    def restore(self) -> RoutineBook:
        return RoutineBook(self.blocks)
