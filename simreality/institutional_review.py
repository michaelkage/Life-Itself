"""Transparent, context-aware institutional review recommendations.

This module converts recorded institutional history into a review *signal*, not
an automatic punishment or a verdict about a person's character. Rules and
context adjustments are explicit inputs so different institutions can behave
differently and decisions can be inspected and replayed.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .routine_institution_ledger import InstitutionalRecord


class ReviewLevel(str, Enum):
    NONE = "none"
    CHECK_IN = "check_in"
    FORMAL_REVIEW = "formal_review"
    URGENT_REVIEW = "urgent_review"


@dataclass(frozen=True)
class ContextAdjustment:
    """Explicit contextual evidence that raises or lowers review pressure."""

    signal_id: str
    adjustment: float
    explanation: str

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, str) or not self.signal_id.strip():
            raise ValueError("signal_id must be a non-empty string")
        if isinstance(self.adjustment, bool) or not isinstance(self.adjustment, (int, float)) or not math.isfinite(self.adjustment):
            raise ValueError("adjustment must be finite")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation must be a non-empty string")


@dataclass(frozen=True)
class InstitutionalReviewPolicy:
    """Configurable review thresholds and history weights for one institution."""

    policy_id: str
    check_in_threshold: float = 1.0
    formal_review_threshold: float = 3.0
    urgent_review_threshold: float = 6.0
    late_arrival_weight: float = 1.0
    missed_appointment_weight: float = 2.0
    delay_minutes_per_point: int = 60
    maximum_delay_points: float = 3.0

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not self.policy_id.strip():
            raise ValueError("policy_id must be a non-empty string")
        numeric = (
            "check_in_threshold", "formal_review_threshold", "urgent_review_threshold",
            "late_arrival_weight", "missed_appointment_weight", "maximum_delay_points",
        )
        for name in numeric:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
        if not (self.check_in_threshold <= self.formal_review_threshold <= self.urgent_review_threshold):
            raise ValueError("review thresholds must be ordered")
        if isinstance(self.delay_minutes_per_point, bool) or not isinstance(self.delay_minutes_per_point, int) or self.delay_minutes_per_point <= 0:
            raise ValueError("delay_minutes_per_point must be a positive integer")


@dataclass(frozen=True)
class ReviewContribution:
    source: str
    amount: float
    explanation: str


@dataclass(frozen=True)
class InstitutionalReviewAssessment:
    institution_id: str
    person_id: str
    policy_id: str
    score: float
    level: ReviewLevel
    contributions: tuple[ReviewContribution, ...]
    note: str = "This is a review recommendation, not a finding of fault or an automatic sanction."


class InstitutionalReviewEvaluator:
    """Pure deterministic evaluation of an institution's explicit review policy."""

    def __init__(self, policy: InstitutionalReviewPolicy) -> None:
        if not isinstance(policy, InstitutionalReviewPolicy):
            raise TypeError("policy must be an InstitutionalReviewPolicy")
        self.policy = policy

    def assess(
        self,
        record: InstitutionalRecord,
        context: tuple[ContextAdjustment, ...] = (),
    ) -> InstitutionalReviewAssessment:
        if not isinstance(record, InstitutionalRecord):
            raise TypeError("record must be an InstitutionalRecord")
        if not isinstance(context, tuple) or any(not isinstance(item, ContextAdjustment) for item in context):
            raise TypeError("context must be a tuple of ContextAdjustment values")
        if len({item.signal_id for item in context}) != len(context):
            raise ValueError("context signal IDs must be unique")

        p = self.policy
        contributions = [
            ReviewContribution("late_arrivals", record.late_arrivals * p.late_arrival_weight,
                               f"{record.late_arrivals} recorded late arrival(s) × {p.late_arrival_weight:g}"),
            ReviewContribution("missed_appointments", record.missed_appointments * p.missed_appointment_weight,
                               f"{record.missed_appointments} recorded missed appointment(s) × {p.missed_appointment_weight:g}"),
        ]
        delay_points = min(record.total_delay_minutes / p.delay_minutes_per_point, p.maximum_delay_points)
        contributions.append(ReviewContribution(
            "recorded_delay", delay_points,
            f"{record.total_delay_minutes} recorded delay minute(s), capped at {p.maximum_delay_points:g} point(s)",
        ))
        for signal in sorted(context, key=lambda item: item.signal_id):
            contributions.append(ReviewContribution(
                f"context:{signal.signal_id}", float(signal.adjustment), signal.explanation,
            ))
        score = max(0.0, sum(item.amount for item in contributions))
        if score >= p.urgent_review_threshold:
            level = ReviewLevel.URGENT_REVIEW
        elif score >= p.formal_review_threshold:
            level = ReviewLevel.FORMAL_REVIEW
        elif score >= p.check_in_threshold:
            level = ReviewLevel.CHECK_IN
        else:
            level = ReviewLevel.NONE
        return InstitutionalReviewAssessment(
            record.institution_id, record.person_id, p.policy_id, score, level, tuple(contributions),
        )
