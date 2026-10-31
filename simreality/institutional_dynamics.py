"""Deterministic institutional decision pressures and transparent option ranking.

This is a decision-support model, not an action executor or a universal morality
system. Leadership priorities, department incentives, scarce resources, political
pressure, employee traits, evidence, and explicit bias cues remain inspectable
inputs. The caller chooses whether an NPC enacts a ranked option.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _unit(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and between 0 and 1")


def _nonnegative(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _weights(values: tuple[tuple[str, float], ...], name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple of (name, weight) pairs")
    names = []
    for item in values:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError(f"{name} entries must be pairs")
        key, value = item
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"{name} keys must be non-empty strings")
        _unit(value, f"{name}[{key}]")
        names.append(key)
    if len(names) != len(set(names)):
        raise ValueError(f"{name} keys must be unique")


@dataclass(frozen=True)
class InstitutionalProfile:
    institution_id: str
    leader_id: str
    leadership_priorities: tuple[tuple[str, float], ...]
    accountability: float = 0.5
    political_pressure: float = 0.0
    budget_pressure: float = 0.5
    staffing_pressure: float = 0.5

    def __post_init__(self) -> None:
        for name in ("institution_id", "leader_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        _weights(self.leadership_priorities, "leadership_priorities")
        for name in ("accountability", "political_pressure", "budget_pressure", "staffing_pressure"):
            _unit(getattr(self, name), name)


@dataclass(frozen=True)
class DepartmentState:
    department_id: str
    priority_weights: tuple[tuple[str, float], ...]
    budget_remaining: float
    staff_available: float
    influence: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.department_id, str) or not self.department_id.strip():
            raise ValueError("department_id must be a non-empty string")
        _weights(self.priority_weights, "priority_weights")
        _nonnegative(self.budget_remaining, "budget_remaining")
        _nonnegative(self.staff_available, "staff_available")
        _unit(self.influence, "influence")


@dataclass(frozen=True)
class InstitutionalEmployee:
    person_id: str
    integrity: float = 0.5
    ambition: float = 0.5
    leadership_loyalty: float = 0.5
    favouritism: float = 0.0
    bias_weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.person_id, str) or not self.person_id.strip():
            raise ValueError("person_id must be a non-empty string")
        for name in ("integrity", "ambition", "leadership_loyalty", "favouritism"):
            _unit(getattr(self, name), name)
        _weights(self.bias_weights, "bias_weights")


@dataclass(frozen=True)
class InstitutionalDecisionOption:
    option_id: str
    department_id: str
    description: str
    budget_cost: float = 0.0
    staff_cost: float = 0.0
    priority_tags: tuple[str, ...] = ()
    evidence_strength: float = 0.5
    minimum_evidence: float = 0.0
    requester_influence: float = 0.0
    public_visibility: float = 0.0
    transparency: float = 0.5
    personal_advantage: float = 0.0
    bias_cues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("option_id", "department_id", "description"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        _nonnegative(self.budget_cost, "budget_cost")
        _nonnegative(self.staff_cost, "staff_cost")
        for name in ("evidence_strength", "minimum_evidence", "requester_influence",
                     "public_visibility", "transparency", "personal_advantage"):
            _unit(getattr(self, name), name)
        for name in ("priority_tags", "bias_cues"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise TypeError(f"{name} must be a tuple of non-empty strings")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")


@dataclass(frozen=True)
class InstitutionalScoreContribution:
    axis: str
    amount: float
    explanation: str


@dataclass(frozen=True)
class InstitutionalOptionAssessment:
    option_id: str
    feasible: bool
    score: float
    contributions: tuple[InstitutionalScoreContribution, ...]
    blockers: tuple[str, ...]


@dataclass(frozen=True)
class InstitutionalDecisionResult:
    institution_id: str
    employee_id: str
    department_id: str
    ranked_options: tuple[InstitutionalOptionAssessment, ...]
    note: str = "Rankings describe configured pressures, not objective right and wrong."


class InstitutionalDecisionEvaluator:
    """Pure ranking of institutional options under explicit local conditions."""

    def evaluate(
        self,
        institution: InstitutionalProfile,
        department: DepartmentState,
        employee: InstitutionalEmployee,
        options: tuple[InstitutionalDecisionOption, ...],
    ) -> InstitutionalDecisionResult:
        if not isinstance(institution, InstitutionalProfile):
            raise TypeError("institution must be an InstitutionalProfile")
        if not isinstance(department, DepartmentState):
            raise TypeError("department must be a DepartmentState")
        if not isinstance(employee, InstitutionalEmployee):
            raise TypeError("employee must be an InstitutionalEmployee")
        if not isinstance(options, tuple) or any(not isinstance(o, InstitutionalDecisionOption) for o in options):
            raise TypeError("options must be a tuple of InstitutionalDecisionOption values")
        if len({o.option_id for o in options}) != len(options):
            raise ValueError("option IDs must be unique")
        if any(o.department_id != department.department_id for o in options):
            raise ValueError("every option must belong to the evaluated department")

        leadership = dict(institution.leadership_priorities)
        departmental = dict(department.priority_weights)
        bias = dict(employee.bias_weights)
        ranked = []
        for option in options:
            blockers = []
            if option.budget_cost > department.budget_remaining:
                blockers.append("department budget is insufficient")
            if option.staff_cost > department.staff_available:
                blockers.append("department staffing is insufficient")
            if option.evidence_strength < option.minimum_evidence:
                blockers.append("minimum evidence threshold is not met")

            contributions = []
            if option.priority_tags:
                values = [(leadership.get(tag, 0.0) + departmental.get(tag, 0.0)) / 2.0
                          for tag in option.priority_tags]
                priority_fit = sum(values) / len(values)
            else:
                priority_fit = 0.0
            contributions.append(InstitutionalScoreContribution(
                "priority_alignment", priority_fit,
                "Mean alignment with leadership and department priorities",
            ))

            budget_ratio = option.budget_cost / max(department.budget_remaining, 1.0)
            staff_ratio = option.staff_cost / max(department.staff_available, 1.0)
            contributions.append(InstitutionalScoreContribution(
                "resource_pressure",
                -(budget_ratio * institution.budget_pressure + staff_ratio * institution.staffing_pressure),
                "Resource costs are weighted by current institutional pressure",
            ))
            evidence_effect = (option.evidence_strength * 2.0 - 1.0) * (0.5 + institution.accountability)
            contributions.append(InstitutionalScoreContribution(
                "evidence_and_accountability", evidence_effect,
                "Evidence strength matters more where accountability is stronger",
            ))
            visibility_effect = option.public_visibility * institution.political_pressure
            contributions.append(InstitutionalScoreContribution(
                "political_pressure", visibility_effect,
                "Public visibility matters only to the extent political pressure is present",
            ))
            transparency_effect = (option.transparency - 0.5) * institution.accountability
            contributions.append(InstitutionalScoreContribution(
                "transparency", transparency_effect,
                "Transparent handling is favoured by stronger accountability",
            ))
            favour_effect = employee.favouritism * option.requester_influence * department.influence
            contributions.append(InstitutionalScoreContribution(
                "preferential_access", favour_effect,
                "Explicit favouritism can amplify a requester's institutional influence",
            ))
            ambition_effect = employee.ambition * option.personal_advantage
            contributions.append(InstitutionalScoreContribution(
                "personal_advantage", ambition_effect,
                "Personal advantage can appeal to an ambitious decision-maker",
            ))
            loyalty_effect = employee.leadership_loyalty * priority_fit
            contributions.append(InstitutionalScoreContribution(
                "leadership_loyalty", loyalty_effect,
                "Leadership loyalty reinforces alignment with stated priorities",
            ))
            integrity_effect = employee.integrity * (option.evidence_strength - option.personal_advantage)
            contributions.append(InstitutionalScoreContribution(
                "integrity", integrity_effect,
                "Integrity rewards evidence-supported choices and resists self-serving advantage",
            ))
            bias_effect = sum(bias.get(cue, 0.0) for cue in option.bias_cues)
            contributions.append(InstitutionalScoreContribution(
                "employee_bias", bias_effect,
                "Only explicitly configured employee bias cues contribute",
            ))

            score = sum(item.amount for item in contributions)
            ranked.append(InstitutionalOptionAssessment(
                option.option_id, not blockers, score, tuple(contributions), tuple(blockers),
            ))
        ranked.sort(key=lambda item: (not item.feasible, -item.score, item.option_id))
        return InstitutionalDecisionResult(
            institution.institution_id, employee.person_id, department.department_id, tuple(ranked),
        )
