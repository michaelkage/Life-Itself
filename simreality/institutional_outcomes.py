"""Evidence-aware effects of public and internal institutional outcomes.

This adapter translates explicitly classified outcomes into political-history
events. Allegations are not findings: only policy rules for the supplied
finding status can change influence, relationships, or leadership priorities.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .institutional_politics import InstitutionalPoliticalEvent, InstitutionalPoliticalLedger


_FINDING_STATUSES = {
    "alleged",
    "corroborated",
    "substantiated",
    "not_substantiated",
    "insufficient_evidence",
    "confirmed",
    "retracted",
    "under_review",
    "dismissed",
}


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _delta(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and between -1 and 1")


@dataclass(frozen=True)
class InstitutionalOutcome:
    outcome_id: str
    institution_id: str
    period_index: int
    outcome_type: str
    finding_status: str
    department_id: str
    related_department_id: str | None = None
    priority_tag: str | None = None
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("outcome_id", "institution_id", "outcome_type", "department_id"):
            _identifier(getattr(self, name), name)
        if isinstance(self.period_index, bool) or not isinstance(self.period_index, int) or self.period_index < 0:
            raise ValueError("period_index must be a non-negative integer")
        if self.finding_status not in _FINDING_STATUSES:
            raise ValueError(f"finding_status must be one of {sorted(_FINDING_STATUSES)}")
        if self.related_department_id is not None:
            _identifier(self.related_department_id, "related_department_id")
            if self.related_department_id == self.department_id:
                raise ValueError("related department must differ from the affected department")
        if self.priority_tag is not None:
            _identifier(self.priority_tag, "priority_tag")
        if not isinstance(self.evidence_ids, tuple) or any(not isinstance(x, str) or not x.strip() for x in self.evidence_ids):
            raise TypeError("evidence_ids must be a tuple of non-empty IDs")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")


@dataclass(frozen=True)
class InstitutionalOutcomeRule:
    outcome_type: str
    finding_status: str
    influence_delta: float = 0.0
    relationship_delta: float = 0.0
    leadership_priority_delta: float = 0.0
    priority_tag: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.outcome_type, "outcome_type")
        if self.finding_status not in _FINDING_STATUSES:
            raise ValueError("unsupported finding_status")
        _delta(self.influence_delta, "influence_delta")
        _delta(self.relationship_delta, "relationship_delta")
        _delta(self.leadership_priority_delta, "leadership_priority_delta")
        if self.relationship_delta != 0.0 and self.priority_tag is not None:
            # priority_tag is reserved for leadership priority changes; relationship
            # targets are supplied by the outcome itself.
            pass
        if self.leadership_priority_delta != 0.0:
            _identifier(self.priority_tag, "priority_tag")
        elif self.priority_tag is not None:
            _identifier(self.priority_tag, "priority_tag")


@dataclass(frozen=True)
class InstitutionalOutcomePolicy:
    policy_id: str
    rules: tuple[InstitutionalOutcomeRule, ...]

    def __post_init__(self) -> None:
        _identifier(self.policy_id, "policy_id")
        if not isinstance(self.rules, tuple) or any(not isinstance(x, InstitutionalOutcomeRule) for x in self.rules):
            raise TypeError("rules must be a tuple of InstitutionalOutcomeRule values")
        keys = [(x.outcome_type, x.finding_status) for x in self.rules]
        if len(keys) != len(set(keys)):
            raise ValueError("policy may define only one rule per outcome type and finding status")


@dataclass(frozen=True)
class InstitutionalOutcomeAssessment:
    outcome_id: str
    policy_id: str
    applied: bool
    influence_delta: float
    relationship_delta: float
    leadership_priority_delta: float
    rationale: str
    event: InstitutionalPoliticalEvent


class InstitutionalOutcomeAdapter:
    """Map explicitly classified outcomes to replay-safe political events."""

    def assess(self, ledger: InstitutionalPoliticalLedger, outcome: InstitutionalOutcome,
               policy: InstitutionalOutcomePolicy) -> InstitutionalOutcomeAssessment:
        if not isinstance(ledger, InstitutionalPoliticalLedger):
            raise TypeError("ledger must be an InstitutionalPoliticalLedger")
        if not isinstance(outcome, InstitutionalOutcome):
            raise TypeError("outcome must be an InstitutionalOutcome")
        if not isinstance(policy, InstitutionalOutcomePolicy):
            raise TypeError("policy must be an InstitutionalOutcomePolicy")
        if outcome.institution_id != ledger.institution_id:
            raise ValueError("outcome belongs to a different institution")

        rule = next((item for item in policy.rules
                     if item.outcome_type == outcome.outcome_type
                     and item.finding_status == outcome.finding_status), None)
        influence_delta = 0.0 if rule is None else rule.influence_delta
        relationship_delta = 0.0 if rule is None else rule.relationship_delta
        priority_delta = 0.0 if rule is None else rule.leadership_priority_delta
        priority_tag = None
        if rule is not None and priority_delta != 0.0:
            priority_tag = rule.priority_tag or outcome.priority_tag
            if priority_tag is None:
                raise ValueError("outcome or rule must supply priority_tag for a leadership priority change")
        if relationship_delta != 0.0 and outcome.related_department_id is None:
            raise ValueError("outcome must name related_department_id for a relationship change")

        signature_data = {
            "outcome": asdict(outcome),
            "policy_id": policy.policy_id,
            "rule": None if rule is None else asdict(rule),
        }
        canonical = json.dumps(signature_data, sort_keys=True, separators=(",", ":"), allow_nan=False)
        signature = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        applied = rule is not None and any((influence_delta, relationship_delta, priority_delta))
        rationale = (
            f"outcome:{outcome.outcome_id};type:{outcome.outcome_type};"
            f"finding:{outcome.finding_status};policy:{policy.policy_id};"
            f"evidence:{','.join(outcome.evidence_ids)};signature:{signature}"
        )
        event = InstitutionalPoliticalEvent(
            event_id=f"outcome:{outcome.outcome_id}",
            institution_id=outcome.institution_id,
            period_index=outcome.period_index,
            department_id=outcome.department_id,
            influence_delta=influence_delta,
            other_department_id=outcome.related_department_id if relationship_delta else None,
            relationship_delta=relationship_delta,
            priority_tag=priority_tag,
            leadership_priority_delta=priority_delta,
            rationale=rationale,
        )
        return InstitutionalOutcomeAssessment(
            outcome.outcome_id, policy.policy_id, applied, influence_delta,
            relationship_delta, priority_delta, rationale, event,
        )

    def commit(self, ledger: InstitutionalPoliticalLedger,
               assessments: tuple[InstitutionalOutcomeAssessment, ...]):
        if not isinstance(ledger, InstitutionalPoliticalLedger):
            raise TypeError("ledger must be an InstitutionalPoliticalLedger")
        if not isinstance(assessments, tuple) or any(not isinstance(x, InstitutionalOutcomeAssessment) for x in assessments):
            raise TypeError("assessments must be a tuple of InstitutionalOutcomeAssessment values")
        if len({x.outcome_id for x in assessments}) != len(assessments):
            raise ValueError("outcome IDs must be unique in a commit batch")
        return ledger.append_many(tuple(x.event for x in assessments))
