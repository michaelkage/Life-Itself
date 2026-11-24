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

    def __post_init__(self):
        if not isinstance(self.cell_id, str) or not self.cell_id.strip():
            raise ValueError("cell_id must be non-empty")
        if not isinstance(self.lod, PopulationLOD):
            raise TypeError("lod must be a PopulationLOD")
        if not isinstance(self.owner_ids, tuple) or any(
            not isinstance(owner, str) or not owner.strip() for owner in self.owner_ids
        ):
            raise ValueError("owner_ids must be a tuple of non-empty strings")
        if tuple(sorted(set(self.owner_ids))) != self.owner_ids:
            raise ValueError("population slice owner IDs must be unique and sorted")


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

    def __post_init__(self):
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("schedule tick must be a non-negative integer")
        if not isinstance(self.slices, tuple) or any(not isinstance(item, PopulationSlice) for item in self.slices):
            raise TypeError("slices must be a tuple of PopulationSlice values")
        if len({(item.cell_id, item.lod) for item in self.slices}) != len(self.slices):
            raise ValueError("schedule contains duplicate cell/LOD slices")
        for name, owners in (("selected_owner_ids", self.selected_owner_ids), ("deferred_owner_ids", self.deferred_owner_ids)):
            if not isinstance(owners, tuple) or any(not isinstance(owner, str) or not owner.strip() for owner in owners):
                raise ValueError(f"{name} must be a tuple of non-empty owner IDs")
            if len(set(owners)) != len(owners):
                raise ValueError(f"{name} must not contain duplicates")
        selected = set(self.selected_owner_ids)
        deferred = set(self.deferred_owner_ids)
        if selected & deferred:
            raise ValueError("selected and deferred owner sets must be disjoint")
        sliced = [owner for item in self.slices for owner in item.owner_ids]
        if len(sliced) != len(set(sliced)) or set(sliced) != selected | deferred:
            raise ValueError("schedule slices must partition selected and deferred owners exactly")
        dormant = {
            owner for item in self.slices if item.lod == PopulationLOD.DORMANT
            for owner in item.owner_ids
        }
        if dormant != deferred:
            raise ValueError("deferred owners must correspond exactly to dormant LOD slices")

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

    def schedule_adaptive(
        self,
        tick: int,
        owner_ids: tuple[str, ...],
        importance: Mapping[str, float],
        *,
        budget_controller,
        lod_policy,
    ):
        """Build a spatial schedule from measured subsystem execution costs.

        The controller receives the full roster as the total work ceiling; it
        apportions that ceiling across active LOD tiers. The resulting budgets
        are still passed through the same canonical schedule validation and
        replay-signature checks as explicitly configured budgets.
        """
        from .population_budget import PopulationBudgetController
        from .population_lod_policy import PopulationLODPolicy
        if not isinstance(budget_controller, PopulationBudgetController):
            raise TypeError("budget_controller must be a PopulationBudgetController")
        if not isinstance(lod_policy, PopulationLODPolicy):
            raise TypeError("lod_policy must be a PopulationLODPolicy")
        if not isinstance(owner_ids, tuple):
            raise TypeError("owner_ids must be a tuple")
        roster_size = len(owner_ids)
        allocation = budget_controller.allocate(
            tick,
            {
                PopulationLOD.FULL: roster_size,
                PopulationLOD.STANDARD: roster_size,
                PopulationLOD.BACKGROUND: roster_size,
                PopulationLOD.DORMANT: 0,
            },
            lod_policy,
            max_total_owners=roster_size,
        )
        schedule = self.schedule(
            tick,
            owner_ids,
            importance,
            full_budget=allocation.full_budget,
            standard_budget=allocation.standard_budget,
            background_budget=allocation.background_budget,
        )
        return schedule, allocation

    def snapshot(self) -> tuple[PopulationSchedule, ...]:
        return tuple(self._history[tick][1] for tick in sorted(self._history))
