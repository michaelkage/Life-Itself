"""Canonical persistence for misconduct reports and review history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .misconduct import (
    MisconductReport, MisconductReportingSystem, MisconductType,
    ReviewDecision, ReviewOutcome,
)
from .world_events import WorldEventLedger


def _report_payload(report: MisconductReport) -> dict:
    return {
        "report_id": report.report_id,
        "filed_tick": report.filed_tick,
        "reporter_id": report.reporter_id,
        "subject_id": report.subject_id,
        "institution_id": report.institution_id,
        "misconduct_type": report.misconduct_type.value,
        "incident_ids": list(report.incident_ids),
        "description": report.description,
        "anonymous": report.anonymous,
    }


def _decision_payload(decision: ReviewDecision) -> dict:
    return {
        "decision_id": decision.decision_id,
        "report_id": decision.report_id,
        "tick": decision.tick,
        "reviewer_id": decision.reviewer_id,
        "outcome": decision.outcome.value,
        "evidence_ids": list(decision.evidence_ids),
        "rationale": decision.rationale,
    }


@dataclass(frozen=True)
class MisconductSnapshot:
    """Versioned, canonical JSON representation of reports and their decisions.

    Restoring against a world-event ledger validates every report incident
    reference. Evidence IDs remain references only; an evidence registry is a
    separate system and is not fabricated by this codec.
    """
    reports: tuple[MisconductReport, ...]
    decisions: tuple[ReviewDecision, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.reports, tuple) or not isinstance(self.decisions, tuple):
            raise ValueError("reports and decisions must be tuples")
        system = MisconductReportingSystem(self.reports, self.decisions)
        reports, decisions = system.snapshot()
        if reports != self.reports or decisions != self.decisions:
            raise ValueError("misconduct snapshot entries must be in canonical order")

    @classmethod
    def capture(cls, system: MisconductReportingSystem) -> "MisconductSnapshot":
        if not isinstance(system, MisconductReportingSystem):
            raise TypeError("system must be a MisconductReportingSystem")
        reports, decisions = system.snapshot()
        return cls(reports, decisions)

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "reports": [_report_payload(item) for item in self.reports],
            "decisions": [_decision_payload(item) for item in self.decisions],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "MisconductSnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported misconduct snapshot schema version")
            reports = tuple(MisconductReport(
                report_id=item["report_id"],
                filed_tick=item["filed_tick"],
                reporter_id=item["reporter_id"],
                subject_id=item["subject_id"],
                institution_id=item["institution_id"],
                misconduct_type=MisconductType(item["misconduct_type"]),
                incident_ids=tuple(item["incident_ids"]),
                description=item["description"],
                anonymous=item.get("anonymous", False),
            ) for item in raw["reports"])
            decisions = tuple(ReviewDecision(
                decision_id=item["decision_id"],
                report_id=item["report_id"],
                tick=item["tick"],
                reviewer_id=item["reviewer_id"],
                outcome=ReviewOutcome(item["outcome"]),
                evidence_ids=tuple(item["evidence_ids"]),
                rationale=item["rationale"],
            ) for item in raw["decisions"])
            return cls(reports, decisions)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid misconduct snapshot") from exc

    def restore(self, events: WorldEventLedger) -> MisconductReportingSystem:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        event_ids = {event.event_id for event in events.snapshot()}
        for report in self.reports:
            missing = sorted(set(report.incident_ids) - event_ids)
            if missing:
                raise ValueError(
                    f"report {report.report_id!r} references missing world events: {missing}"
                )
        return MisconductReportingSystem(self.reports, self.decisions)
