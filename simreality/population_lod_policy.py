"""Subsystem-specific fidelity policies for each population LOD tier."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .population_spatial import PopulationLOD


@dataclass(frozen=True)
class SubsystemLODPolicy:
    subsystem_id: str
    cadence_ticks: int
    enabled: bool = True

    def __post_init__(self):
        if not isinstance(self.subsystem_id, str) or not self.subsystem_id.strip():
            raise ValueError("subsystem_id must be non-empty")
        if isinstance(self.cadence_ticks, bool) or not isinstance(self.cadence_ticks, int) or self.cadence_ticks < 1:
            raise ValueError("cadence_ticks must be a positive integer")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be boolean")


class PopulationLODPolicy:
    """Resolve subsystem cadence and enablement without hidden simulation work."""

    def __init__(self, policies: Mapping[PopulationLOD, tuple[SubsystemLODPolicy, ...]]):
        if not isinstance(policies, Mapping) or set(policies) != set(PopulationLOD):
            raise ValueError("policies must define every PopulationLOD tier exactly")
        self._policies = {}
        for tier, entries in policies.items():
            if not isinstance(tier, PopulationLOD) or not isinstance(entries, tuple):
                raise TypeError("each tier must map to a tuple of SubsystemLODPolicy values")
            if any(not isinstance(item, SubsystemLODPolicy) for item in entries):
                raise TypeError("tier policies must contain SubsystemLODPolicy values")
            if len({item.subsystem_id for item in entries}) != len(entries):
                raise ValueError("subsystem IDs must be unique within each LOD tier")
            self._policies[tier] = {item.subsystem_id: item for item in entries}

    def due_subsystems(self, tier: PopulationLOD, tick: int) -> tuple[str, ...]:
        if not isinstance(tier, PopulationLOD):
            raise TypeError("tier must be a PopulationLOD")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        return tuple(sorted(
            subsystem_id for subsystem_id, policy in self._policies[tier].items()
            if policy.enabled and tick % policy.cadence_ticks == 0
        ))

    def policy_for(self, tier: PopulationLOD, subsystem_id: str) -> SubsystemLODPolicy | None:
        if not isinstance(tier, PopulationLOD):
            raise TypeError("tier must be a PopulationLOD")
        return self._policies[tier].get(subsystem_id)


def default_population_lod_policy() -> PopulationLODPolicy:
    """Balanced defaults; callers may replace them with measured workload policy."""
    return PopulationLODPolicy({
        PopulationLOD.FULL: (
            SubsystemLODPolicy("action", 1),
            SubsystemLODPolicy("decision", 1),
            SubsystemLODPolicy("economy", 1),
            SubsystemLODPolicy("memory", 1),
            SubsystemLODPolicy("presence", 1),
            SubsystemLODPolicy("routine", 1),
            SubsystemLODPolicy("social", 1),
            SubsystemLODPolicy("travel", 1),
        ),
        PopulationLOD.STANDARD: (
            SubsystemLODPolicy("action", 1),
            SubsystemLODPolicy("decision", 1),
            SubsystemLODPolicy("economy", 2),
            SubsystemLODPolicy("memory", 1),
            SubsystemLODPolicy("presence", 1),
            SubsystemLODPolicy("routine", 1),
            SubsystemLODPolicy("social", 2),
            SubsystemLODPolicy("travel", 1),
        ),
        PopulationLOD.BACKGROUND: (
            SubsystemLODPolicy("action", 1),
            SubsystemLODPolicy("decision", 4),
            SubsystemLODPolicy("economy", 4),
            SubsystemLODPolicy("memory", 4),
            SubsystemLODPolicy("presence", 1),
            SubsystemLODPolicy("routine", 2),
            SubsystemLODPolicy("social", 4),
            SubsystemLODPolicy("travel", 1),
        ),
        PopulationLOD.DORMANT: (
            SubsystemLODPolicy("action", 1),
            SubsystemLODPolicy("decision", 1, False),
            SubsystemLODPolicy("economy", 1, False),
            SubsystemLODPolicy("memory", 1, False),
            SubsystemLODPolicy("presence", 1),
            SubsystemLODPolicy("routine", 1, False),
            SubsystemLODPolicy("social", 1, False),
            SubsystemLODPolicy("travel", 1, True),
        ),
    })
