"""Deterministic, evidence-aware reporting for institutional misconduct.

A report records an allegation, not a verdict. Evidence references and explicit
review decisions are append-only. A report is never substantiated merely because
it was filed, and a review decision cannot silently rewrite its prior history.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MisconductType(str, Enum):
    DISCRIMINATION = "discrimination"
    RACIAL_DISCRIMINATION = "racial_discrimination"
    CORRUPTION = "corruption"
    ABUSE_OF_AUTHORITY = "abuse_of_authority"
    NEGLECT_OF_DUTY = "neglect_of_duty"
    BRIBERY = "bribery"
    FAVOURITISM = "favouritism"


class ReviewOutcome(str, Enum):
    FILED = "filed"
    UNDER_REVIEW = "under_review"
    SUBSTANTIATED = "substantiated"
    NOT_SUBSTANTIATED = "not_substantiated"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class MisconductReport:
    report_id: str
    filed_tick: int
    reporter_id: str | None
    subject_id: str
    institution_id: str
    misconduct_type: MisconductType
    incident_ids: tuple[str, ...]
    description: str
    anonymous: bool = False

    def __post_init__(self) -> None:
        for name in ("report_id", "subject_id", "institution_id", "description"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.reporter_id is not None and (not isinstance(self.reporter_id, str) or not self.reporter_id.strip()):
            raise ValueError("reporter_id must be None or a non-empty string")
        if isinstance(self.filed_tick, bool) or not isinstance(self.filed_tick, int) or self.filed_tick < 0:
            raise ValueError("filed_tick must be a non-negative integer")
        if not isinstance(self.misconduct_type, MisconductType):
            raise ValueError("misconduct_type must be a MisconductType")
        if not isinstance(self.anonymous, bool):
            raise ValueError("anonymous must be a boolean")
        if self.anonymous and self.reporter_id is not None:
            raise ValueError("anonymous reports must not expose reporter_id")
        if not self.anonymous and self.reporter_id is None:
            raise ValueError("non-anonymous reports require reporter_id")
        if not isinstance(self.incident_ids, tuple) or not self.incident_ids:
            raise ValueError("incident_ids must be a non-empty tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.incident_ids):
            raise ValueError("incident IDs must be non-empty strings")
        if len(set(self.incident_ids)) != len(self.incident_ids):
            raise ValueError("incident IDs must be unique within a report")


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: str
    report_id: str
    tick: int
    reviewer_id: str
    outcome: ReviewOutcome
    evidence_ids: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        for name in ("decision_id", "report_id", "reviewer_id", "rationale"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(self.outcome, ReviewOutcome):
            raise ValueError("outcome must be a ReviewOutcome")
        if self.outcome is ReviewOutcome.FILED:
            raise ValueError("review decisions cannot use FILED as an outcome")
        if not isinstance(self.evidence_ids, tuple):
            raise ValueError("evidence_ids must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.evidence_ids):
            raise ValueError("evidence IDs must be non-empty strings")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence IDs must be unique")


@dataclass(frozen=True)
class ReportStatus:
    report: MisconductReport
    outcome: ReviewOutcome
    latest_decision: ReviewDecision | None
    decision_history: tuple[ReviewDecision, ...]


class MisconductReportingSystem:
    """Append-only reports and review decisions with stable, idempotent replay.

    The system does not discover misconduct, decide whether an allegation is
    true, or infer guilt from identity or a complaint count. Reviewers must add
    explicit decisions with cited evidence and a rationale.
    """

    def __init__(self, reports: Iterable[MisconductReport] = (),
                 decisions: Iterable[ReviewDecision] = ()) -> None:
        self._reports: dict[str, MisconductReport] = {}
        self._decisions: dict[str, ReviewDecision] = {}
        self._decision_order: list[str] = []
        self.add_reports(reports)
        self.add_decisions(decisions)

    def add_report(self, report: MisconductReport) -> MisconductReport:
        self.add_reports((report,))
        return self._reports[report.report_id]

    def add_reports(self, reports: Iterable[MisconductReport]) -> tuple[MisconductReport, ...]:
        items = tuple(reports)
        seen: set[str] = set()
        for report in items:
            if not isinstance(report, MisconductReport):
                raise TypeError("reports must contain MisconductReport instances")
            if report.report_id in seen:
                raise ValueError(f"duplicate report ID in batch: {report.report_id}")
            seen.add(report.report_id)
            prior = self._reports.get(report.report_id)
            if prior is not None and prior != report:
                raise ValueError(f"report ID reused with different content: {report.report_id}")
        for report in items:
            self._reports.setdefault(report.report_id, report)
        return tuple(self._reports[report.report_id] for report in items)

    def add_decision(self, decision: ReviewDecision) -> ReviewDecision:
        self.add_decisions((decision,))
        return self._decisions[decision.decision_id]

    def add_decisions(self, decisions: Iterable[ReviewDecision]) -> tuple[ReviewDecision, ...]:
        items = tuple(decisions)
        seen: set[str] = set()
        last_tick_by_report: dict[str, int] = {}
        for decision in items:
            if not isinstance(decision, ReviewDecision):
                raise TypeError("decisions must contain ReviewDecision instances")
            if decision.decision_id in seen:
                raise ValueError(f"duplicate decision ID in batch: {decision.decision_id}")
            seen.add(decision.decision_id)
            if decision.report_id not in self._reports:
                raise ValueError(f"decision references unknown report: {decision.report_id}")
            report = self._reports[decision.report_id]
            if decision.tick < report.filed_tick:
                raise ValueError("review decision cannot predate its report")
            prior = self._decisions.get(decision.decision_id)
            if prior is not None:
                if prior != decision:
                    raise ValueError(f"decision ID reused with different content: {decision.decision_id}")
                # Exact replay is idempotent even after later decisions were recorded.
                continue
            if decision.report_id not in last_tick_by_report:
                existing = [self._decisions[key] for key in self._decision_order
                            if self._decisions[key].report_id == decision.report_id]
                last_tick_by_report[decision.report_id] = existing[-1].tick if existing else report.filed_tick
            if decision.tick < last_tick_by_report[decision.report_id]:
                raise ValueError("review decisions must not move backward in time")
            last_tick_by_report[decision.report_id] = decision.tick
        for decision in items:
            if decision.decision_id not in self._decisions:
                self._decisions[decision.decision_id] = decision
                self._decision_order.append(decision.decision_id)
        return tuple(self._decisions[decision.decision_id] for decision in items)

    def status(self, report_id: str) -> ReportStatus:
        if report_id not in self._reports:
            raise KeyError(report_id)
        history = tuple(
            self._decisions[key] for key in self._decision_order
            if self._decisions[key].report_id == report_id
        )
        latest = history[-1] if history else None
        return ReportStatus(
            self._reports[report_id],
            latest.outcome if latest else ReviewOutcome.FILED,
            latest,
            history,
        )

    def reports(self, *, subject_id: str | None = None,
                institution_id: str | None = None) -> tuple[ReportStatus, ...]:
        values = [
            self.status(report_id) for report_id in self._reports
            if (subject_id is None or self._reports[report_id].subject_id == subject_id)
            and (institution_id is None or self._reports[report_id].institution_id == institution_id)
        ]
        return tuple(sorted(values, key=lambda item: (item.report.filed_tick, item.report.report_id)))

    def snapshot(self) -> tuple[tuple[MisconductReport, ...], tuple[ReviewDecision, ...]]:
        reports = tuple(sorted(self._reports.values(), key=lambda r: (r.filed_tick, r.report_id)))
        decisions = tuple(self._decisions[key] for key in self._decision_order)
        return reports, decisions
