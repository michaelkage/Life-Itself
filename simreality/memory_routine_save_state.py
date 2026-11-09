"""Canonical JSON persistence for explicit NPC memory/location associations."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .memory_location_book import MemoryLocationAssociationBook
from .memory_routines import MemoryLocationAssociation


@dataclass(frozen=True)
class MemoryLocationAssociationSnapshot:
    entries: tuple[tuple[str, MemoryLocationAssociation], ...]

    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, book: MemoryLocationAssociationBook) -> "MemoryLocationAssociationSnapshot":
        if not isinstance(book, MemoryLocationAssociationBook):
            raise TypeError("book must be a MemoryLocationAssociationBook")
        return cls(book.snapshot())

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise ValueError("entries must be a tuple")
        keys = []
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ValueError("each entry must contain owner ID and association")
            owner_id, association = entry
            if not isinstance(owner_id, str) or not owner_id.strip():
                raise ValueError("owner_id must be a non-empty string")
            if not isinstance(association, MemoryLocationAssociation):
                raise ValueError("association must be a MemoryLocationAssociation")
            keys.append((owner_id, association.association_id))
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("association entries must be uniquely sorted")

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "entries": [
                {"owner_id": owner, "association": asdict(association)}
                for owner, association in self.entries
            ],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "MemoryLocationAssociationSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported memory-location snapshot schema")
            entries = tuple(
                (item["owner_id"], MemoryLocationAssociation(**item["association"]))
                for item in raw["entries"]
            )
            return cls(entries)
        except ValueError:
            raise
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid memory-location association snapshot") from exc

    def restore(self) -> MemoryLocationAssociationBook:
        return MemoryLocationAssociationBook(self.entries)
