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
from .beliefs import Evidence, BeliefState
from .campaign_knowledge import CampaignKnowledgeLedger



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
    archived_life_simulations: dict[str, str] = field(default_factory=dict, repr=False)
    shared_knowledge: CampaignKnowledgeLedger = field(default_factory=CampaignKnowledgeLedger, repr=False)

    def begin_first_life(self, character_id: str) -> None:
        if self.active_world.life is not None:
            raise RuntimeError("the active world already has a campaign life")
        self.active_world.start_new_life(character_id)

    @staticmethod
    def _validate_life_simulation(simulation, world: PersistentWorld) -> None:
        from .life_simulation import LifeSimulation
        if not isinstance(simulation, LifeSimulation):
            raise TypeError("life_simulation must be a LifeSimulation")
        if simulation.world is not world:
            raise ValueError("LifeSimulation must share the campaign timeline PersistentWorld")

    def record_death(self, cause: str, *, life_simulation=None) -> WorldArchive:
        """Resolve life-owned responsibilities, then freeze the authoritative world."""
        if life_simulation is not None:
            self._validate_life_simulation(life_simulation, self.active_world)
            if self.active_world.life is None or self.active_world.life.state is not LifeState.ACTIVE:
                raise RuntimeError("only an active life can die")
            life_simulation.resolve_after_death(self.active_world.life.character_id)
        return self.active_world.kill_current_life(cause)

    def continue_as_ghost(self, *, life_simulation=None) -> None:
        if life_simulation is not None:
            self._validate_life_simulation(life_simulation, self.active_world)
        self.active_world.enter_ghost_state()

    def start_fresh_world(self, character_id: str, *, label: str | None = None,
                          life_simulation=None) -> None:
        """Archive world and service state together before creating a clean timeline."""
        old = self.active_world
        if old.life is None or old.life.state not in (LifeState.SPECTATOR, LifeState.GHOST):
            raise RuntimeError("a fresh world can only begin after the current life has ended")
        if life_simulation is not None:
            self._validate_life_simulation(life_simulation, old)
        if not old.archives:
            raise RuntimeError("the ended timeline has no death archive identity")
        archive_id = old.archives[-1].archive_id
        if any(item.archive_id == archive_id for item in self.archived_worlds):
            raise ValueError(f"duplicate archived timeline ID: {archive_id}")
        service_snapshot = None
        if life_simulation is not None:
            from .life_simulation_save_state import LifeSimulationSnapshot
            service_snapshot = LifeSimulationSnapshot.capture(life_simulation).to_json()
        archived_world = deepcopy(old)
        self.archived_worlds.append(ArchivedTimeline(
            archive_id=archive_id,
            label=label or f"World at day {old.day}",
            archived_day=old.day,
            reason=old.life.death_cause or "life-ended",
            world=archived_world,
        ))
        if service_snapshot is not None:
            self.archived_life_simulations[archive_id] = service_snapshot
        fresh = PersistentWorld(day=0)
        fresh.start_new_life(character_id)
        self.active_world = fresh

    def start_fresh_life(self, character_id: str, life_simulation, *,
                         seed: int = 1, label: str | None = None):
        """Archive the old service and return a new service bound to the fresh world."""
        self._validate_life_simulation(life_simulation, self.active_world)
        self.start_fresh_world(character_id, label=label, life_simulation=life_simulation)
        from .life_simulation import LifeSimulation
        return LifeSimulation(self.active_world, seed=seed)

    def visit_archive_runtime(self, archive_id: str):
        """Return one detached archived world and its service, sharing that exact world."""
        from .life_simulation_save_state import LifeSimulationSnapshot
        for archived in self.archived_worlds:
            if archived.archive_id == archive_id:
                world = deepcopy(archived.world)
                payload = self.archived_life_simulations.get(archive_id)
                simulation = (LifeSimulationSnapshot.from_json(payload).restore(world)
                              if payload is not None else None)
                return world, simulation
        raise KeyError(archive_id)

    def visit_archive(self, archive_id: str) -> PersistentWorld:
        """Return a detached copy so inspection cannot mutate the preserved archive."""
        world, _ = self.visit_archive_runtime(archive_id)
        return world

    def record_shared_evidence(self, evidence: Evidence) -> Evidence:
        """Record attributable world evidence at campaign scope, not as a personal memory."""
        return self.shared_knowledge.add(evidence)

    def shared_belief(self, claim_id: str) -> BeliefState:
        """Retrieve a cross-life claim assessment with its evidence IDs."""
        return self.shared_knowledge.belief(claim_id)

    def shared_evidence_for(self, claim_id: str) -> tuple[Evidence, ...]:
        """Return provenance records available to every life in this campaign."""
        return self.shared_knowledge.evidence_for(claim_id)

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
        payload = {
            "schema_version": 1,
            "active_world": encode(self.active_world),
            "archived_worlds": [encode(item) for item in self.archived_worlds],
        }
        if self.archived_life_simulations:
            payload["archived_life_simulations"] = dict(sorted(self.archived_life_simulations.items()))
        knowledge = self.shared_knowledge.to_json()
        if knowledge != CampaignKnowledgeLedger().to_json():
            payload["shared_knowledge"] = json.loads(knowledge)
        return json.dumps(payload, sort_keys=True, allow_nan=False)

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
        archived_ids = {item.archive_id for item in archived}
        service_states = raw.get("archived_life_simulations", {})
        if not isinstance(service_states, dict) or any(
            not isinstance(key, str) or key not in archived_ids or not isinstance(value, str)
            for key, value in service_states.items()
        ):
            raise ValueError("archived LifeSimulation states must reference known timeline IDs")
        from .life_simulation_save_state import LifeSimulationSnapshot
        archive_worlds = {item.archive_id: item.world for item in archived}
        for archive_id, snapshot_json in service_states.items():
            LifeSimulationSnapshot.from_json(snapshot_json).restore(archive_worlds[archive_id])
        return cls(
            active_world=load_world(raw["active_world"]),
            archived_worlds=archived,
            archived_life_simulations=dict(service_states),
            shared_knowledge=CampaignKnowledgeLedger.from_json(json.dumps(
                raw.get("shared_knowledge", {"schema_version": 1, "evidence": []}),
                sort_keys=True, separators=(",", ":"), allow_nan=False)),
        )
