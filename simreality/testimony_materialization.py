"""Replay-safe materialization of answered inquiries into testimony records."""
from __future__ import annotations

from .testimony import TestimonyLedger, TestimonyRecord
from .testimony_inquiries import TestimonyInquiryLedger


class TestimonyMaterializationAdapter:
    """Append an answered inquiry to the shared testimony pipeline.

    The caller chooses the testimony ID and recording hour. Refusals and
    unanswered inquiries remain in the inquiry ledger and produce no record.
    The testimony ledger's stable-ID conflict checks make exact replay safe.
    """

    def materialize(
        self,
        inquiries: TestimonyInquiryLedger,
        testimony: TestimonyLedger,
        inquiry_id: str,
        testimony_id: str,
        recorded_hour: float,
        *,
        decay_rate_per_hour: float = 0.01,
    ) -> TestimonyRecord | None:
        if not isinstance(inquiries, TestimonyInquiryLedger):
            raise TypeError("inquiries must be a TestimonyInquiryLedger")
        if not isinstance(testimony, TestimonyLedger):
            raise TypeError("testimony must be a TestimonyLedger")
        if not isinstance(testimony_id, str) or not testimony_id.strip():
            raise ValueError("testimony_id must be non-empty")
        record = inquiries.to_testimony_record(
            inquiry_id, testimony_id, recorded_hour,
            decay_rate_per_hour=decay_rate_per_hour,
        )
        if record is None:
            return None
        return testimony.append(record)
