"""Deterministic competition for institutional budgets and staffing.

Allocation is a transparent planning result. It does not spend resources or
change department state; a world-level owner must commit the result explicitly.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _finite_nonnegative(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _unit(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between 0 and 1")


@dataclass(frozen=True)
class DepartmentResourceRequest:
    department_id: str
    budget_requested: float
    staff_requested: float
    priority_tags: tuple[str, ...]
    service_impact: float = 0.5
    urgency: float = 0.0
    influence: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.department_id, str) or not self.department_id.strip():
            raise ValueError("department_id must be a non-empty string")
        _finite_nonnegative(self.budget_requested, "budget_requested")
        _finite_nonnegative(self.staff_requested, "staff_requested")
        if not isinstance(self.priority_tags, tuple) or any(not isinstance(x, str) or not x.strip() for x in self.priority_tags):
            raise TypeError("priority_tags must be a tuple of non-empty strings")
        if len(set(self.priority_tags)) != len(self.priority_tags):
            raise ValueError("priority_tags must not contain duplicates")
        for name in ("service_impact", "urgency", "influence"):
            _unit(getattr(self, name), name)
        if self.budget_requested == 0 and self.staff_requested == 0:
            raise ValueError("a request must ask for budget, staff, or both")


@dataclass(frozen=True)
class ResourceAllocationPolicy:
    policy_id: str
    priority_weight: float = 0.5
    service_impact_weight: float = 0.25
    urgency_weight: float = 0.15
    influence_weight: float = 0.1

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        weights = (self.priority_weight, self.service_impact_weight, self.urgency_weight, self.influence_weight)
        for value in weights:
            _finite_nonnegative(value, "allocation weight")
        if sum(weights) <= 0:
            raise ValueError("at least one allocation weight must be positive")


@dataclass(frozen=True)
class DepartmentAllocation:
    department_id: str
    request_score: float
    allocation_ratio: float
    budget_allocated: float
    staff_allocated: float
    budget_unmet: float
    staff_unmet: float
    score_contributions: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ResourceAllocationPlan:
    institution_id: str
    period_id: str
    policy_id: str
    total_budget: float
    total_staff: float
    allocations: tuple[DepartmentAllocation, ...]
    note: str = "This is a proposed allocation; resources change only when a caller commits it."


class InstitutionalResourceAllocator:
    """Rank requests and distribute scarce resources by a stable priority score."""

    def plan(
        self,
        institution_id: str,
        period_id: str,
        total_budget: float,
        total_staff: float,
        requests: tuple[DepartmentResourceRequest, ...],
        leadership_priorities: tuple[tuple[str, float], ...],
        policy: ResourceAllocationPolicy,
    ) -> ResourceAllocationPlan:
        for name, value in (("institution_id", institution_id), ("period_id", period_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        _finite_nonnegative(total_budget, "total_budget")
        _finite_nonnegative(total_staff, "total_staff")
        if not isinstance(policy, ResourceAllocationPolicy):
            raise TypeError("policy must be a ResourceAllocationPolicy")
        if not isinstance(requests, tuple) or any(not isinstance(r, DepartmentResourceRequest) for r in requests):
            raise TypeError("requests must be a tuple of DepartmentResourceRequest values")
        if len({r.department_id for r in requests}) != len(requests):
            raise ValueError("each department may submit only one request per period")
        if not isinstance(leadership_priorities, tuple):
            raise TypeError("leadership_priorities must be a tuple")
        priorities = {}
        for item in leadership_priorities:
            if not isinstance(item, tuple) or len(item) != 2:
                raise TypeError("leadership priorities must contain pairs")
            tag, weight = item
            if not isinstance(tag, str) or not tag.strip() or tag in priorities:
                raise ValueError("leadership priority tags must be non-empty and unique")
            _unit(weight, f"leadership_priorities[{tag}]")
            priorities[tag] = float(weight)

        w = policy
        weight_total = w.priority_weight + w.service_impact_weight + w.urgency_weight + w.influence_weight
        scored = []
        for request in requests:
            priority = sum(priorities.get(tag, 0.0) for tag in request.priority_tags) / max(1, len(request.priority_tags))
            parts = (
                ("leadership_priority", priority * w.priority_weight),
                ("service_impact", request.service_impact * w.service_impact_weight),
                ("urgency", request.urgency * w.urgency_weight),
                ("department_influence", request.influence * w.influence_weight),
            )
            score = sum(value for _, value in parts) / weight_total
            scored.append((request, score, parts))
        scored.sort(key=lambda item: (-item[1], item[0].department_id))

        remaining_budget = float(total_budget)
        remaining_staff = float(total_staff)
        allocations = []
        for request, score, parts in scored:
            budget_ratio = 1.0 if request.budget_requested == 0 else min(1.0, remaining_budget / request.budget_requested)
            staff_ratio = 1.0 if request.staff_requested == 0 else min(1.0, remaining_staff / request.staff_requested)
            ratio = min(budget_ratio, staff_ratio)
            budget = request.budget_requested * ratio
            staff = request.staff_requested * ratio
            remaining_budget = max(0.0, remaining_budget - budget)
            remaining_staff = max(0.0, remaining_staff - staff)
            allocations.append(DepartmentAllocation(
                request.department_id, score, ratio, budget, staff,
                request.budget_requested - budget, request.staff_requested - staff, parts,
            ))
        return ResourceAllocationPlan(
            institution_id, period_id, policy.policy_id, float(total_budget), float(total_staff),
            tuple(allocations),
        )
