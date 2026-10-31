"""Institution-specific response options generated from review assessments.

This layer presents available next steps; it never selects or executes one.
A human or NPC decision-maker must choose, and the caller must record that
choice as a separate world event if it is enacted.
"""
from __future__ import annotations

from dataclasses import dataclass

from .institutional_review import InstitutionalReviewAssessment, ReviewLevel


@dataclass(frozen=True)
class InstitutionalResponseOption:
    option_id: str
    description: str
    supportive: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.option_id, str) or not self.option_id.strip():
            raise ValueError("option_id must be a non-empty string")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        if not isinstance(self.supportive, bool):
            raise TypeError("supportive must be a bool")


@dataclass(frozen=True)
class InstitutionalResponsePolicy:
    policy_id: str
    options_by_level: tuple[tuple[ReviewLevel, tuple[InstitutionalResponseOption, ...]], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.options_by_level, tuple):
            raise TypeError("options_by_level must be a tuple")
        levels = [entry[0] for entry in self.options_by_level if isinstance(entry, tuple) and len(entry) == 2]
        if len(levels) != len(self.options_by_level) or any(not isinstance(level, ReviewLevel) for level in levels):
            raise TypeError("each policy entry must contain a ReviewLevel and options tuple")
        if len(set(levels)) != len(levels):
            raise ValueError("each review level may appear only once")
        if set(levels) != set(ReviewLevel):
            raise ValueError("policy must define every review level")
        for level, options in self.options_by_level:
            if not isinstance(options, tuple) or any(not isinstance(option, InstitutionalResponseOption) for option in options):
                raise TypeError("each level must map to a tuple of InstitutionalResponseOption values")
            ids = [option.option_id for option in options]
            if len(ids) != len(set(ids)):
                raise ValueError("option IDs must be unique within each review level")

    def options_for(self, level: ReviewLevel) -> tuple[InstitutionalResponseOption, ...]:
        if not isinstance(level, ReviewLevel):
            raise TypeError("level must be a ReviewLevel")
        return dict(self.options_by_level)[level]


@dataclass(frozen=True)
class InstitutionalResponsePlan:
    institution_id: str
    person_id: str
    assessment_policy_id: str
    response_policy_id: str
    review_level: ReviewLevel
    options: tuple[InstitutionalResponseOption, ...]
    note: str = "Options only: no action is selected or executed."


class InstitutionalResponsePlanner:
    """Pure deterministic mapping from an assessment to institution options."""

    def __init__(self, policy: InstitutionalResponsePolicy) -> None:
        if not isinstance(policy, InstitutionalResponsePolicy):
            raise TypeError("policy must be an InstitutionalResponsePolicy")
        self.policy = policy

    def plan(self, assessment: InstitutionalReviewAssessment) -> InstitutionalResponsePlan:
        if not isinstance(assessment, InstitutionalReviewAssessment):
            raise TypeError("assessment must be an InstitutionalReviewAssessment")
        return InstitutionalResponsePlan(
            assessment.institution_id,
            assessment.person_id,
            assessment.policy_id,
            self.policy.policy_id,
            assessment.level,
            self.policy.options_for(assessment.level),
        )
