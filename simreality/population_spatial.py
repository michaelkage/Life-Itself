"""Deterministic spatial partitioning and budgeted population level-of-detail.

The scheduler consumes authoritative symbolic location IDs and explicit
importance scores. It does not infer coordinates, proximity, or encounters.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Mapping

from .presence import PresenceLedger


class PopulationLOD(IntEnum):
    DORMANT = 0
    BACKGROUND = 1
    STANDARD = 2
    FULL = 3


@dataclass(frozen=True)
class PopulationSlice:
    cell_id: str
    lod: PopulationLOD
    owner_ids: tuple[str, ...]


@dataclass(frozen=True)
class PopulationSubsystemSlice:
    subsystem_id: str
    owner_ids: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.subsystem_id, str) or not self.subsystem_id.strip():
            raise ValueError("subsystem_id must be non-empty")
        if not isinstance(self.owner_ids, tuple) or any(
            not isinstance(owner, str) or not owner.strip() for owner in self.owner_ids
        ):
            raise ValueError("owner_ids must be a tuple of non-empty strings")
        if tuple(sorted(set(self.owner_ids))) != self.owner_ids:
            raise ValueError("subsystem owner IDs must be unique and sorted")


@dataclass(frozen=True)
class PopulationSchedule:
    tick: int
    slices: tuple[PopulationSlice, ...]
    selected_owner_ids: tuple[str, ...]
    deferred_owner_ids: tuple[str, ...]

    def subsystem_slices(self, policy) -> tuple[PopulationSubsystemSlice, ...]:
        """Resolve LOD cadence into stable owner batches for each subsystem."""
        from .population_lod_policy import PopulationLODPolicy
        if not isinstance(policy, PopulationLODPolicy):
            raise TypeError("policy must be a PopulationLODPolicy")
        owners_by_subsystem = {}
        for population_slice in self.slices:
            for subsystem_id in policy.due_subsystems(population_slice.lod, self.tick):
                owners_by_subsystem.setdefault(subsystem_id, set()).update(population_slice.owner_ids)
        return tuple(
            PopulationSubsystemSlice(subsystem_id, tuple(sorted(owner_ids)))
            for subsystem_id, owner_ids in sorted(owners_by_subsystem.items())
        )


class PopulationSpatialScheduler:
    """Assign stable spatial partitions and LOD tiers under explicit budgets.

    Owners in transit are partitioned by their current route node, while
    stationary owners use their authoritative presence location. Missing
    presence is an error rather than an invented default location.
    """

    def __init__(self, presence: PresenceLedger) -> None:
        if not isinstance(presence, PresenceLedger):
            raise TypeError("presence must be a PresenceLedger")
        self.presence = presence
        self._history: dict[int, tuple[tuple, PopulationSchedule]] = {}

    def schedule(
        self,
        tick: int,
        owner_ids: tuple[str, ...],
        importance: Mapping[str, float],
        *,
        full_budget: int,
        standard_budget: int,
        background_budget: int,
    ) -> PopulationSchedule:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(owner_ids, tuple) or any(not isinstance(x, str) or not x.strip() for x in owner_ids):
            raise ValueError("owner_ids must be a tuple of non-empty IDs")
        if len(set(owner_ids)) != len(owner_ids):
            raise ValueError("owner_ids must be unique")
        for name, value in (("full_budget", full_budget), ("standard_budget", standard_budget),
                            ("background_budget", background_budget)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(importance, Mapping) or set(importance) != set(owner_ids):
            raise ValueError("importance must provide exactly one score for every owner")
        clean = {}
        for owner, score in importance.items():
            if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0.0 <= score <= 1.0:
                raise ValueError("importance scores must be numeric values in [0, 1]")
            clean[owner] = float(score)
        locations = {}
        for owner in owner_ids:
            record = self.presence.get(owner)
            if record is None:
                raise KeyError(f"missing authoritative presence for NPC: {owner}")
            locations[owner] = record.location_id
        signature = (
            tuple(sorted(owner_ids)), tuple(sorted(clean.items())),
            full_budget, standard_budget, background_budget,
            tuple(sorted(locations.items())),
        )
        previous = self._history.get(tick)
        if previous is not None:
            if previous[0] != signature:
                raise ValueError(f"conflicting population schedule replay: {tick}")
            return previous[1]
        if self._history and tick <= max(self._history):
            raise ValueError("new population schedules must advance monotonically")

        # Rank globally so budgets are predictable, then group by symbolic cell.
        ranked = sorted(owner_ids, key=lambda owner: (-clean[owner], owner))
        tiers = {}
        for index, owner in enumerate(ranked):
            if index < full_budget:
                tier = PopulationLOD.FULL
            elif index < full_budget + standard_budget:
                tier = PopulationLOD.STANDARD
            elif index < full_budget + standard_budget + background_budget:
                tier = PopulationLOD.BACKGROUND
            else:
                tier = PopulationLOD.DORMANT
            tiers[owner] = tier

        grouped = {}
        for owner in sorted(owner_ids):
            grouped.setdefault(locations[owner], {}).setdefault(tiers[owner], []).append(owner)
        slices = tuple(
            PopulationSlice(cell, lod, tuple(grouped[cell][lod]))
            for cell in sorted(grouped)
            for lod in sorted(grouped[cell], reverse=True)
        )
        selected = tuple(owner for owner in ranked if tiers[owner] != PopulationLOD.DORMANT)
        deferred = tuple(owner for owner in ranked if tiers[owner] == PopulationLOD.DORMANT)
        result = PopulationSchedule(tick, slices, selected, deferred)
        self._history[tick] = (signature, result)
        return result

    def snapshot(self) -> tuple[PopulationSchedule, ...]:
        return tuple(self._history[tick][1] for tick in sorted(self._history))
