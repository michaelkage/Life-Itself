import unittest

from simreality.testimony_followups import TestimonyFollowUp
from simreality.testimony_inquiries import TestimonyInquiryLedger
from simreality.testimony_inquiry_adapter import TestimonyInquiryAdapter


class TestimonyInquiryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.proposal = TestimonyFollowUp(
            event_id="evt", attribute_key="coat", witness_id="alice",
            testimony_id="t1", reported_value="green", belief_confidence=None,
            testimony_confidence=0.8, priority=0.8,
            reason="conflicting accounts need clarification",
        )
        self.adapter = TestimonyInquiryAdapter()
        self.ledger = TestimonyInquiryLedger()

    def test_selected_proposal_becomes_question_without_answering_it(self):
        inquiry = self.adapter.ask(self.ledger, self.proposal, "q1", 12)
        self.assertEqual((inquiry.event_id, inquiry.witness_id, inquiry.attribute_key),
                         ("evt", "alice", "coat"))
        self.assertEqual(inquiry.asked_tick, 12)
        self.assertEqual(self.ledger.inquiries(), (inquiry,))
        self.assertEqual(self.ledger.responses(), ())

    def test_exact_replay_is_idempotent(self):
        first = self.adapter.ask(self.ledger, self.proposal, "q1", 12)
        second = self.adapter.ask(self.ledger, self.proposal, "q1", 12)
        self.assertIs(first, second)

    def test_reusing_id_for_different_question_is_rejected(self):
        self.adapter.ask(self.ledger, self.proposal, "q1", 12)
        other = TestimonyFollowUp(
            event_id="evt", attribute_key="coat", witness_id="bob",
            testimony_id="t2", reported_value="black", belief_confidence=None,
            testimony_confidence=0.7, priority=0.7, reason="conflict",
        )
        with self.assertRaises(ValueError):
            self.adapter.ask(self.ledger, other, "q1", 12)

    def test_invalid_tick_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter.ask(self.ledger, self.proposal, "q1", -1)


if __name__ == "__main__":
    unittest.main()
