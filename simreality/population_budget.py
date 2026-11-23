"""Measured-cost population LOD budget allocation.

The controller converts observed subsystem wall time into deterministic
per-owner cost estimates, then allocates a bounded number of FULL, STANDARD
and BACKGROUND owners for the next population schedule. It never changes
simulation state or infers owner importance.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping

from .population_spatial import PopulationLOD
from .population_lod_policy import PopulationLODPolicy


@dataclass(frozen=True)
class PopulationBudgetAllocation:
    tick: int
    full_budget: int
    standard_budget: int
    background_budget: int
    estimated_tick_ms: float
    target_tick_ms: float
    utilization_target: float
    tier_costs_ms: tuple[tuple[PopulationLOD, float], ...]

    def __post_init__(self):
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("allocation tick must be a non-negative integer")
        for name, value in (
            ("full_budget", self.full_budget),
            ("standard_budget", self.standard_budget),
            ("background_budget", self.background_budget),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name, value in (
            ("estimated_tick_ms", self.estimated_tick_ms),
            ("target_tick_ms", self.target_tick_ms),
            ("utilization_target", self.utilization_target),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.estimated_tick_ms < 0 or self.target_tick_ms <= 0:
            raise ValueError("estimated cost must be non-negative and target cost positive")
        if not 0 < self.utilization_target <= 1:
            raise ValueError("utilization_target must be in (0, 1]")
        if not isinstance(self.tier_costs_ms, tuple):
            raise TypeError("tier_costs_ms must be a tuple")
        if tuple(tier for tier, _ in self.tier_costs_ms) != (
            PopulationLOD.FULL, PopulationLOD.STANDARD, PopulationLOD.BACKGROUND,
        ):
            raise ValueError("tier costs must list active tiers in canonical order")
        for tier, cost in self.tier_costs_ms:
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost <= 0:
                raise ValueError(f"{tier.name} tier cost must be finite and positive")


class PopulationBudgetController:
    """EWMA cost model and deterministic weighted-fair LOD budget allocator."""

    SCHEMA_VERSION = 1

    def __init__(
        self,
        target_tick_ms: float,
        *,
        utilization_target: float = 0.8,
        ewma_alpha: float = 0.25,
        tier_weights: Mapping[PopulationLOD, float] | None = None,
        default_subsystem_cost_ms: float = 0.25,
    ):
        self._finite_positive("target_tick_ms", target_tick_ms)
        self._finite_positive("default_subsystem_cost_ms", default_subsystem_cost_ms)
        if isinstance(utilization_target, bool) or not isinstance(utilization_target, (int, float)) or not math.isfinite(utilization_target) or not 0 < utilization_target <= 1:
            raise ValueError("utilization_target must be finite and in (0, 1]")
        if isinstance(ewma_alpha, bool) or not isinstance(ewma_alpha, (int, float)) or not math.isfinite(ewma_alpha) or not 0 < ewma_alpha <= 1:
            raise ValueError("ewma_alpha must be finite and in (0, 1]")
        weights = tier_weights or {
            PopulationLOD.FULL: 4.0,
            PopulationLOD.STANDARD: 2.0,
            PopulationLOD.BACKGROUND: 1.0,
        }
        if not isinstance(weights, Mapping) or set(weights) != {
            PopulationLOD.FULL, PopulationLOD.STANDARD, PopulationLOD.BACKGROUND,
        }:
            raise ValueError("tier_weights must define FULL, STANDARD and BACKGROUND")
        normalized = {}
        for tier, weight in weights.items():
            if not isinstance(tier, PopulationLOD) or tier == PopulationLOD.DORMANT:
                raise ValueError("tier weights may only define active PopulationLOD tiers")
            self._finite_positive(f"{tier.name} tier weight", weight)
            normalized[tier] = float(weight)
        self.target_tick_ms = float(target_tick_ms)
        self.utilization_target = float(utilization_target)
        self.ewma_alpha = float(ewma_alpha)
        self.tier_weights = normalized
        self.default_subsystem_cost_ms = float(default_subsystem_cost_ms)
        self._subsystem_costs: dict[str, float] = {}
        self._sample_counts: dict[str, int] = {}

    @staticmethod
    def _finite_positive(name: str, value) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")

    def record_phase_sample(self, subsystem_id: str, elapsed_ms: float, owner_count: int) -> None:
        """Update per-owner EWMA cost from one completed subsystem phase."""
        if not isinstance(subsystem_id, str) or not subsystem_id.strip():
            raise ValueError("subsystem_id must be non-empty")
        if isinstance(elapsed_ms, bool) or not isinstance(elapsed_ms, (int, float)) or not math.isfinite(elapsed_ms) or elapsed_ms < 0:
            raise ValueError("elapsed_ms must be finite and non-negative")
        if isinstance(owner_count, bool) or not isinstance(owner_count, int) or owner_count < 0:
            raise ValueError("owner_count must be a non-negative integer")
        if owner_count == 0:
            return
        observed = max(float(elapsed_ms) / owner_count, 1e-9)
        prior = self._subsystem_costs.get(subsystem_id)
        self._subsystem_costs[subsystem_id] = (
            observed if prior is None
            else self.ewma_alpha * observed + (1.0 - self.ewma_alpha) * prior
        )
        self._sample_counts[subsystem_id] = self._sample_counts.get(subsystem_id, 0) + 1

    def subsystem_cost_ms(self, subsystem_id: str) -> float:
        if not isinstance(subsystem_id, str) or not subsystem_id.strip():
            raise ValueError("subsystem_id must be non-empty")
        return self._subsystem_costs.get(subsystem_id, self.default_subsystem_cost_ms)

    def allocate(
        self,
        tick: int,
        population_counts: Mapping[PopulationLOD, int],
        policy: PopulationLODPolicy,
        *,
        max_total_owners: int | None = None,
    ) -> PopulationBudgetAllocation:
        """Allocate owner slots under the measured tick-time budget.

        Weighted-fair selection favors higher-detail tiers while dividing
        available work according to both tier weight and measured marginal
        cost. Equal scores deterministically favor the higher LOD tier.
        """
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(population_counts, Mapping) or set(population_counts) != set(PopulationLOD):
            raise ValueError("population_counts must define every PopulationLOD tier")
        counts = {}
        for tier, count in population_counts.items():
            if not isinstance(tier, PopulationLOD):
                raise TypeError("population count keys must be PopulationLOD values")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("population counts must be non-negative integers")
            counts[tier] = count
        if not isinstance(policy, PopulationLODPolicy):
            raise TypeError("policy must be a PopulationLODPolicy")
        if max_total_owners is None:
            max_total_owners = sum(counts.values())
        if isinstance(max_total_owners, bool) or not isinstance(max_total_owners, int) or max_total_owners < 0:
            raise ValueError("max_total_owners must be a non-negative integer")
        if max_total_owners > sum(counts.values()):
            raise ValueError("max_total_owners cannot exceed the sum of tier capacities")

        active_tiers = (
            PopulationLOD.FULL, PopulationLOD.STANDARD, PopulationLOD.BACKGROUND,
        )
        tier_costs = {}
        for tier in active_tiers:
            subsystem_ids = policy.due_subsystems(tier, tick)
            tier_costs[tier] = sum(
                self.subsystem_cost_ms(subsystem_id) for subsystem_id in subsystem_ids
            )
            if tier_costs[tier] <= 0:
                tier_costs[tier] = 1e-9

        capacity = self.target_tick_ms * self.utilization_target
        budgets = {tier: 0 for tier in active_tiers}
        estimated = 0.0
        while sum(budgets.values()) < max_total_owners:
            candidates = [
                tier for tier in active_tiers
                if budgets[tier] < counts[tier]
                and estimated + tier_costs[tier] <= capacity + 1e-12
            ]
            if not candidates:
                break
            tier = max(
                candidates,
                key=lambda candidate: (
                    self.tier_weights[candidate]
                    / ((budgets[candidate] + 1) * tier_costs[candidate]),
                    int(candidate),
                ),
            )
            budgets[tier] += 1
            estimated += tier_costs[tier]

        return PopulationBudgetAllocation(
            tick=tick,
            full_budget=budgets[PopulationLOD.FULL],
            standard_budget=budgets[PopulationLOD.STANDARD],
            background_budget=budgets[PopulationLOD.BACKGROUND],
            estimated_tick_ms=estimated,
            target_tick_ms=self.target_tick_ms,
            utilization_target=self.utilization_target,
            tier_costs_ms=tuple((tier, tier_costs[tier]) for tier in active_tiers),
        )

    def to_json(self) -> str:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "config": {
                "target_tick_ms": self.target_tick_ms,
                "utilization_target": self.utilization_target,
                "ewma_alpha": self.ewma_alpha,
                "tier_weights": {tier.name: self.tier_weights[tier] for tier in sorted(self.tier_weights)},
                "default_subsystem_cost_ms": self.default_subsystem_cost_ms,
            },
            "subsystem_costs": dict(sorted(self._subsystem_costs.items())),
            "sample_counts": dict(sorted(self._sample_counts.items())),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "PopulationBudgetController":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported population budget snapshot schema")
            config = raw["config"]
            if not isinstance(config, dict) or not isinstance(config.get("tier_weights"), dict):
                raise ValueError("invalid population budget controller configuration")
            weights = {
                PopulationLOD[name]: value
                for name, value in config["tier_weights"].items()
            }
            controller = cls(
                config["target_tick_ms"],
                utilization_target=config["utilization_target"],
                ewma_alpha=config["ewma_alpha"],
                tier_weights=weights,
                default_subsystem_cost_ms=config["default_subsystem_cost_ms"],
            )
            costs = raw["subsystem_costs"]
            counts = raw["sample_counts"]
            if not isinstance(costs, dict) or not isinstance(counts, dict) or set(costs) != set(counts):
                raise ValueError("invalid population budget sample maps")
            for subsystem_id, cost in costs.items():
                if not isinstance(subsystem_id, str) or not subsystem_id.strip():
                    raise ValueError("invalid subsystem cost key")
                if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost <= 0:
                    raise ValueError(f"cost for {subsystem_id} must be finite and positive")
                cost = float(cost)
                sample_count = counts[subsystem_id]
                if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 1:
                    raise ValueError("sample counts must be positive integers")
                controller._subsystem_costs[subsystem_id] = float(cost)
                controller._sample_counts[subsystem_id] = sample_count
            return controller
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, AttributeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid population budget controller snapshot") from exc
