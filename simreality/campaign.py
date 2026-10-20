"""Campaign-level world separation for Life Itself.

A dead character's world can continue in spectator/ghost mode. Choosing a new life
starts a fresh active world while retaining prior worlds as read-only archives.
This manager deliberately separates world timelines from character lifetimes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from typing import Any
import json

from .health_life import CampaignLife, LifeState, PersistentWorld, WorldArchive


@dataclass
class ArchivedTimeline:
    archive_id: str
    label: str
    archived_day: int
    reason: str
    world: PersistentWorld


@dataclass
class LifeItselfCampaign:
    active_world: PersistentWorld = field(default_factory=PersistentWorld)
    archived_worlds: list[ArchivedTimeline] = field(default_factory=list)

    def begin_first_life(self, character_id: str) -> None:
        if self.active_world.life is not None:
            raise RuntimeError("the active world already has a campaign life")
        self.active_world.start_new_life(character_id)

    def record_death(self, cause: str) -> WorldArchive:
        """End the playable life and snapshot its world before any transition."""
        return self.active_world.kill_current_life(cause)

    def continue_as_ghost(self) -> None:
        self.active_world.enter_ghost_state()

    def start_fresh_world(self, character_id: str, *, label: str | None = None) -> None:
        """Archive the old timeline, then create a separate new world and life."""
        old = self.active_world
        if old.life is None or old.life.state not in (LifeState.SPECTATOR, LifeState.GHOST):
            raise RuntimeError("a fresh world can only begin after the current life has ended")
        archive_id = old.archives[-1].archive_id if old.archives else f"world-day-{old.day}"
        self.archived_worlds.append(ArchivedTimeline(
            archive_id=archive_id,
            label=label or f"World at day {old.day}",
            archived_day=old.day,
            reason=old.life.death_cause or "life-ended",
            world=deepcopy(old),
        ))
        fresh = PersistentWorld(day=0)
        fresh.start_new_life(character_id)
        self.active_world = fresh

    def visit_archive(self, archive_id: str) -> PersistentWorld:
        """Return a detached copy so inspection cannot mutate the preserved archive."""
        for archived in self.archived_worlds:
            if archived.archive_id == archive_id:
                return deepcopy(archived.world)
        raise KeyError(archive_id)

    def advance_day(self) -> None:
        self.active_world.advance_day()

    def to_json(self) -> str:
        def encode(value: Any) -> Any:
            from enum import Enum
            if isinstance(value, Enum):
                return value.value
            if hasattr(value, "__dataclass_fields__"):
                return {key: encode(item) for key, item in value.__dict__.items()}
            if isinstance(value, dict):
                return {key: encode(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [encode(item) for item in value]
            return value
        return json.dumps({
            "schema_version": 1,
            "active_world": encode(self.active_world),
            "archived_worlds": [encode(item) for item in self.archived_worlds],
        }, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "LifeItselfCampaign":
        raw = json.loads(payload)
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported campaign schema version")

        def load_world(data: dict[str, Any]) -> PersistentWorld:
            return PersistentWorld.from_json(json.dumps({
                "schema_version": 1,
                "world": data,
            }))

        archived = []
        for item in raw.get("archived_worlds", []):
            archived.append(ArchivedTimeline(
                archive_id=item["archive_id"],
                label=item["label"],
                archived_day=item["archived_day"],
                reason=item["reason"],
                world=load_world(item["world"]),
            ))
        return cls(
            active_world=load_world(raw["active_world"]),
            archived_worlds=archived,
        )
