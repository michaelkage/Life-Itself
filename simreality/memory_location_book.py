"""Persistent, owner-scoped links between NPC memories and routine locations."""
from __future__ import annotations

from typing import Iterable

from .memory_routines import MemoryLocationAssociation


class MemoryLocationAssociationBook:
    """Store explicit memory/location links without inferring personal experiences."""

    def __init__(self, entries: Iterable[tuple[str, MemoryLocationAssociation]] = ()) -> None:
        self._entries: dict[tuple[str, str], MemoryLocationAssociation] = {}
        for owner_id, association in entries:
            self.add(owner_id, association)

    def add(self, owner_id: str, association: MemoryLocationAssociation) -> None:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(association, MemoryLocationAssociation):
            raise TypeError("association must be a MemoryLocationAssociation")
        key = (owner_id, association.association_id)
        if key in self._entries:
            raise ValueError(f"duplicate association ID for owner: {association.association_id}")
        self._entries[key] = association

    def remove(self, owner_id: str, association_id: str) -> bool:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        if not isinstance(association_id, str) or not association_id.strip():
            raise ValueError("association_id must be a non-empty string")
        return self._entries.pop((owner_id, association_id), None) is not None

    def for_owner(self, owner_id: str) -> tuple[MemoryLocationAssociation, ...]:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        return tuple(self._entries[key] for key in sorted(self._entries) if key[0] == owner_id)

    def snapshot(self) -> tuple[tuple[str, MemoryLocationAssociation], ...]:
        return tuple((owner, self._entries[(owner, association_id)])
                     for owner, association_id in sorted(self._entries))
