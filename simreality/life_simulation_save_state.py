"""Versioned persistence for LifeSimulation-owned state.

PersistentWorld remains authoritative for money, health, obligations, trust, stress,
life state, and day. This codec stores only the service-owned layer and its RNG state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any

from .health_life import PersistentWorld
from .life_simulation import (
    DailyLifeRecord, GhostDecision, GhostWindow, LifeSimulation, PersonProfile,
    RecoveryEstimate, ResponsibilityOutcome, ResponsibilityResolution, Treatment,
)


def _tuple_tree(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_tree(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_tuple_tree(item) for item in value)
    return value


@dataclass(frozen=True)
class LifeSimulationSnapshot:
    """Versioned, JSON-safe snapshot of state owned by one LifeSimulation."""

    people: tuple[dict[str, Any], ...]
    treatments: tuple[dict[str, Any], ...]
    recovery_estimates: tuple[dict[str, Any], ...]
    daily_records: tuple[dict[str, Any], ...]
    ghost_windows: tuple[dict[str, Any], ...]
    ghost_action_log: tuple[dict[str, Any], ...]
    care_providers: tuple[tuple[str, tuple[str, ...]], ...]
    resolutions: tuple[dict[str, Any], ...]
    random_state: Any

    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, simulation: LifeSimulation) -> "LifeSimulationSnapshot":
        if not isinstance(simulation, LifeSimulation):
            raise TypeError("simulation must be a LifeSimulation")
        for key, profile in simulation.people.items():
            if key != profile.character_id:
                raise ValueError("LifeSimulation person keys must match profile character IDs")
        recovery_records = []
        for key, estimate in sorted(simulation.recovery_estimates.items()):
            owners = [owner for owner in simulation.people
                      if key == f"{owner}:{estimate.condition_id}"]
            if len(owners) != 1:
                raise ValueError(f"recovery estimate has no unique owner: {key}")
            recovery_records.append({
                "character_id": owners[0], **asdict(estimate),
            })
        return cls(
            people=tuple(
                {"character_id": item.character_id, "personality": dict(item.personality),
                 "memories": dict(item.memories), "relationships": dict(item.relationships),
                 "alive": item.alive, "estate_money": item.estate_money, "care_need": item.care_need}
                for _, item in sorted(simulation.people.items())
            ),
            treatments=tuple(
                {"character_id": owner, **asdict(item)}
                for owner, items in sorted(simulation.treatments.items()) for item in items
            ),
            recovery_estimates=tuple(recovery_records),
            daily_records=tuple(asdict(item) for item in simulation.daily_records),
            ghost_windows=tuple({
                "start_hour": item.start_hour, "end_hour": item.end_hour,
                "influence_strength": item.influence_strength,
                "permitted_actions": list(item.permitted_actions),
            } for item in simulation.ghost_windows),
            ghost_action_log=tuple(asdict(item) for item in simulation.ghost_action_log),
            care_providers=tuple((owner, tuple(providers))
                                 for owner, providers in sorted(simulation.care_providers.items())),
            resolutions=tuple({
                "obligation_id": item.obligation_id, "outcome": item.outcome.value,
                "responsible_person": item.responsible_person,
                "amount_paid": item.amount_paid, "trust_change": item.trust_change,
            } for item in simulation.resolutions),
            random_state=simulation.random.getstate(),
        )

    def to_json(self) -> str:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "people": list(self.people),
            "treatments": list(self.treatments),
            "recovery_estimates": list(self.recovery_estimates),
            "daily_records": list(self.daily_records),
            "ghost_windows": list(self.ghost_windows),
            "ghost_action_log": list(self.ghost_action_log),
            "care_providers": [[owner, list(providers)] for owner, providers in self.care_providers],
            "resolutions": list(self.resolutions),
            "random_state": self.random_state,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "LifeSimulationSnapshot":
        try:
            raw = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid LifeSimulation snapshot JSON") from exc
        expected = {
            "schema_version", "people", "treatments", "recovery_estimates",
            "daily_records", "ghost_windows", "ghost_action_log",
            "care_providers", "resolutions", "random_state",
        }
        if not isinstance(raw, dict) or set(raw) != expected:
            raise ValueError("LifeSimulation snapshot has an invalid field set")
        if raw["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported LifeSimulation snapshot schema version")
        collections = expected - {"schema_version", "random_state"}
        if any(not isinstance(raw[name], list) for name in collections):
            raise ValueError("LifeSimulation snapshot collections must be arrays")
        if not isinstance(raw["random_state"], list):
            raise ValueError("LifeSimulation random state must be an array")
        providers = []
        for item in raw["care_providers"]:
            if (not isinstance(item, list) or len(item) != 2
                    or not isinstance(item[0], str) or not isinstance(item[1], list)
                    or any(not isinstance(provider, str) for provider in item[1])):
                raise ValueError("invalid care provider entry")
            providers.append((item[0], tuple(item[1])))
        return cls(
            people=tuple(raw["people"]), treatments=tuple(raw["treatments"]),
            recovery_estimates=tuple(raw["recovery_estimates"]),
            daily_records=tuple(raw["daily_records"]), ghost_windows=tuple(raw["ghost_windows"]),
            ghost_action_log=tuple(raw["ghost_action_log"]), care_providers=tuple(providers),
            resolutions=tuple(raw["resolutions"]), random_state=_tuple_tree(raw["random_state"]),
        )

    def restore(self, world: PersistentWorld) -> LifeSimulation:
        """Bind service-owned state to an independently restored authoritative world."""
        if not isinstance(world, PersistentWorld):
            raise TypeError("world must be a PersistentWorld")
        simulation = LifeSimulation(world)
        for raw in self.people:
            if not isinstance(raw, dict) or set(raw) != {
                "character_id", "personality", "memories", "relationships",
                "alive", "estate_money", "care_need",
            }:
                raise ValueError("invalid person profile in LifeSimulation snapshot")
            profile = PersonProfile(**raw)
            if (profile.character_id not in world.health or profile.character_id not in world.money
                    or profile.character_id not in world.stress):
                raise ValueError(f"LifeSimulation person is missing from PersistentWorld state: {profile.character_id}")
            if profile.character_id in simulation.people:
                raise ValueError(f"duplicate person profile: {profile.character_id}")
            simulation.people[profile.character_id] = profile

        for raw in self.treatments:
            data = dict(raw)
            owner = data.pop("character_id")
            treatment = Treatment(**data)
            if owner not in simulation.people:
                raise ValueError(f"treatment references an unknown person: {owner}")
            if not any(item.condition_id == treatment.condition_id
                       for item in world.health[owner].conditions):
                raise ValueError(f"treatment references an unknown condition: {treatment.condition_id}")
            existing = simulation.treatments.setdefault(owner, [])
            if any(item.treatment_id == treatment.treatment_id for item in existing):
                raise ValueError(f"duplicate treatment ID in snapshot: {treatment.treatment_id}")
            existing.append(treatment)

        for raw in self.recovery_estimates:
            data = dict(raw)
            owner = data.pop("character_id")
            estimate = RecoveryEstimate(**data)
            if owner not in simulation.people or owner not in world.health:
                raise ValueError(f"recovery estimate references an unknown person: {owner}")
            if not any(c.condition_id == estimate.condition_id for c in world.health[owner].conditions):
                raise ValueError(f"recovery estimate references an unknown condition: {estimate.condition_id}")
            key = f"{owner}:{estimate.condition_id}"
            if key in simulation.recovery_estimates:
                raise ValueError(f"duplicate recovery estimate: {key}")
            simulation.recovery_estimates[key] = estimate

        simulation.daily_records = [DailyLifeRecord(**item) for item in self.daily_records]
        simulation.ghost_windows = [GhostWindow(
            start_hour=item["start_hour"], end_hour=item["end_hour"],
            influence_strength=item["influence_strength"],
            permitted_actions=tuple(item["permitted_actions"]),
        ) for item in self.ghost_windows]
        simulation.ghost_action_log = [GhostDecision(**item) for item in self.ghost_action_log]
        simulation.care_providers = {owner: list(providers) for owner, providers in self.care_providers}
        for raw in self.resolutions:
            item = dict(raw)
            item["outcome"] = ResponsibilityOutcome(item["outcome"])
            resolution = ResponsibilityResolution(**item)
            if not any(obligation.obligation_id == resolution.obligation_id
                       for obligation in world.obligations):
                raise ValueError(f"resolution references an unknown world obligation: {resolution.obligation_id}")
            if any(existing.obligation_id == resolution.obligation_id for existing in simulation.resolutions):
                raise ValueError(f"duplicate responsibility resolution: {resolution.obligation_id}")
            simulation.resolutions.append(resolution)
        try:
            simulation.random.setstate(self.random_state)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid LifeSimulation random state") from exc
        return simulation
