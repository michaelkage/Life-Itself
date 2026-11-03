"""Explicit bridge from ranked investigation proposals to player-authorized questions."""
from __future__ import annotations

from .testimony_followups import TestimonyFollowUp
from .testimony_inquiries import TestimonyInquiry, TestimonyInquiryLedger


class TestimonyInquiryAdapter:
    """Turn one selected proposal into a persisted question; never auto-ask."""

    def ask(
        self,
        ledger: TestimonyInquiryLedger,
        follow_up: TestimonyFollowUp,
        inquiry_id: str,
        asked_tick: int,
    ) -> TestimonyInquiry:
        if not isinstance(ledger, TestimonyInquiryLedger):
            raise TypeError("ledger must be TestimonyInquiryLedger")
        if not isinstance(follow_up, TestimonyFollowUp):
            raise TypeError("follow_up must be TestimonyFollowUp")
        if not isinstance(inquiry_id, str) or not inquiry_id.strip():
            raise ValueError("inquiry_id must be non-empty")
        if isinstance(asked_tick, bool) or not isinstance(asked_tick, int) or asked_tick < 0:
            raise ValueError("asked_tick must be a non-negative integer")
        inquiry = TestimonyInquiry(
            inquiry_id=inquiry_id,
            event_id=follow_up.event_id,
            witness_id=follow_up.witness_id,
            attribute_key=follow_up.attribute_key,
            asked_tick=asked_tick,
        )
        return ledger.append_inquiry(inquiry)
