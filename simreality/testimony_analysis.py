"""Deterministic comparison of independently recorded witness accounts."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .testimony import TestimonyLedger, TestimonyRecord


@dataclass(frozen=True)
class TestimonyMatch:
    event_id: str
    attribute_key: str
    witness_ids: tuple[str, str]
    testimony_ids: tuple[str, str]
    values: tuple[str | int | float | bool | None, str | int | float | bool | None]
    confidence: tuple[float, float]


@dataclass(frozen=True)
class InvestigationReport:
    event_id: str
    inquiry_hour: float
    accounts_considered: tuple[str, ...]
    corroborations: tuple[TestimonyMatch, ...]
    contradictions: tuple[TestimonyMatch, ...]


class TestimonyAnalyzer:
    """Compare only details explicitly stated by distinct witnesses.

    An omitted detail is unknown, not disagreement. Confidence is reported as
    time-decayed reliability metadata; it does not decide whether values match.
    """

    def analyze(
        self,
        ledger: TestimonyLedger,
        event_id: str,
        inquiry_hour: float,
    ) -> InvestigationReport:
        if not isinstance(ledger, TestimonyLedger):
            raise TypeError("ledger must be a TestimonyLedger")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("event_id must be non-empty")
        if isinstance(inquiry_hour, bool) or not isinstance(inquiry_hour, (int, float)) or not math.isfinite(inquiry_hour):
            raise ValueError("inquiry_hour must be finite")

        records = tuple(r for r in ledger.snapshot() if r.event_id == event_id)
        if any(inquiry_hour < r.recorded_hour for r in records):
            raise ValueError("inquiry_hour cannot precede a relevant testimony record")

        # A witness may have multiple account records, but never gets compared
        # against themself. Each detail is indexed by its objective attribute key.
        by_attribute: dict[str, list[tuple[TestimonyRecord, object]]] = {}
        for record in records:
            for detail in record.details:
                by_attribute.setdefault(detail.attribute_key, []).append((record, detail))

        corroborations: list[TestimonyMatch] = []
        contradictions: list[TestimonyMatch] = []
        for attribute_key in sorted(by_attribute):
            entries = sorted(
                by_attribute[attribute_key],
                key=lambda pair: (pair[0].witness_id, pair[0].testimony_id, pair[1].detail_id),
            )
            for i, (first_record, first_detail) in enumerate(entries):
                for second_record, second_detail in entries[i + 1:]:
                    if first_record.witness_id == second_record.witness_id:
                        continue
                    # Canonical witness ordering makes output stable regardless
                    # of insertion order.
                    if first_record.witness_id < second_record.witness_id:
                        left_record, left_detail = first_record, first_detail
                        right_record, right_detail = second_record, second_detail
                    else:
                        left_record, left_detail = second_record, second_detail
                        right_record, right_detail = first_record, first_detail
                    left_value, right_value = left_detail.value, right_detail.value
                    match = TestimonyMatch(
                        event_id=event_id,
                        attribute_key=attribute_key,
                        witness_ids=(left_record.witness_id, right_record.witness_id),
                        testimony_ids=(left_record.testimony_id, right_record.testimony_id),
                        values=(left_value, right_value),
                        confidence=(
                            left_record.confidence_at(left_detail, inquiry_hour),
                            right_record.confidence_at(right_detail, inquiry_hour),
                        ),
                    )
                    if left_value == right_value:
                        corroborations.append(match)
                    else:
                        contradictions.append(match)

        key = lambda m: (m.attribute_key, m.witness_ids, m.testimony_ids, repr(m.values))
        return InvestigationReport(
            event_id=event_id,
            inquiry_hour=float(inquiry_hour),
            accounts_considered=tuple(sorted(r.testimony_id for r in records)),
            corroborations=tuple(sorted(corroborations, key=key)),
            contradictions=tuple(sorted(contradictions, key=key)),
        )
