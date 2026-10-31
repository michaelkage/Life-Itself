"""Bridge reviewed misconduct reports into institutional political history.

The report and each later review decision remain separate dated outcomes.
Filing a report never implies substantiation; policy rules decide whether any
finding status has political effects.
"""
from __future__ import annotations

from .institutional_outcomes import (
    InstitutionalOutcome, InstitutionalOutcomeAdapter,
    InstitutionalOutcomeAssessment, InstitutionalOutcomePolicy,
)
from .institutional_politics import InstitutionalPoliticalLedger
from .misconduct import ReportStatus, ReviewOutcome


class MisconductPoliticalBridge:
    """Translate one report's explicit review history into political assessments."""

    _FINDING_STATUS = {
        ReviewOutcome.FILED: "alleged",
        ReviewOutcome.UNDER_REVIEW: "under_review",
        ReviewOutcome.SUBSTANTIATED: "substantiated",
        ReviewOutcome.NOT_SUBSTANTIATED: "not_substantiated",
        ReviewOutcome.INSUFFICIENT_EVIDENCE: "insufficient_evidence",
        ReviewOutcome.DISMISSED: "dismissed",
    }

    def __init__(self, outcomes: InstitutionalOutcomeAdapter | None = None) -> None:
        self.outcomes = outcomes or InstitutionalOutcomeAdapter()

    def assess_status(
        self,
        ledger: InstitutionalPoliticalLedger,
        status: ReportStatus,
        *,
        department_id: str,
        policy: InstitutionalOutcomePolicy,
    ) -> tuple[InstitutionalOutcomeAssessment, ...]:
        if not isinstance(ledger, InstitutionalPoliticalLedger):
            raise TypeError("ledger must be an InstitutionalPoliticalLedger")
        if not isinstance(status, ReportStatus):
            raise TypeError("status must be a ReportStatus")
        if not isinstance(department_id, str) or not department_id.strip():
            raise ValueError("department_id must be a non-empty string")
        report = status.report
        if report.institution_id != ledger.institution_id:
            raise ValueError("report belongs to a different institution")

        outcome_type = f"misconduct:{report.misconduct_type.value}"
        assessments = []
        report_outcome = InstitutionalOutcome(
            outcome_id=f"misconduct-report:{report.report_id}",
            institution_id=report.institution_id,
            period_index=report.filed_tick,
            outcome_type=outcome_type,
            finding_status="alleged",
            department_id=department_id,
            evidence_ids=report.incident_ids,
        )
        assessments.append(self.outcomes.assess(ledger, report_outcome, policy))

        for decision in status.decision_history:
            outcome = InstitutionalOutcome(
                outcome_id=f"misconduct-review:{decision.decision_id}",
                institution_id=report.institution_id,
                period_index=decision.tick,
                outcome_type=outcome_type,
                finding_status=self._FINDING_STATUS[decision.outcome],
                department_id=department_id,
                evidence_ids=tuple(sorted(set(report.incident_ids + decision.evidence_ids))),
            )
            assessments.append(self.outcomes.assess(ledger, outcome, policy))
        return tuple(assessments)

    def commit(self, ledger: InstitutionalPoliticalLedger,
               assessments: tuple[InstitutionalOutcomeAssessment, ...]):
        return self.outcomes.commit(ledger, assessments)
