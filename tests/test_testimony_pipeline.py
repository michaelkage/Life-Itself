import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger
from simreality.testimony import TestimonyLedger, TestimonyRecord, TestimonyDetail
from simreality.testimony_inquiries import TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse
from simreality.testimony_pipeline import InquiryInvestigationPipeline


class InquiryInvestigationPipelineTests(unittest.TestCase):
    def test_answer_flows_through_analysis_and_observer_beliefs(self):
        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("q1", "evt", "alice", "coat", 1),
        ))
        inquiries.append_response(TestimonyResponse("q1", 2, True, "green", 0.9))
        testimony = TestimonyLedger((
            TestimonyRecord("t-bob", "evt", "bob", 1, 0.0, 0.0,
                (TestimonyDetail("d-bob", "coat", "black", 0.8),), ()),
        ))
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        result = InquiryInvestigationPipeline().process(
            inquiries, testimony, beliefs, "q1", "t-alice", 3.0,
            "observer", 4,
        )
        self.assertEqual(result.materialized.testimony_id, "t-alice")
        self.assertEqual(len(result.report.contradictions), 1)
        self.assertEqual(len(result.belief_states), 2)
        self.assertEqual(len(beliefs.beliefs_for("observer")), 2)

    def test_refusal_does_not_create_testimony_or_claim(self):
        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("q1", "evt", "alice", "coat", 1),
        ))
        inquiries.append_response(TestimonyResponse("q1", 2, False, None, 0.0))
        testimony = TestimonyLedger()
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        result = InquiryInvestigationPipeline().process(
            inquiries, testimony, beliefs, "q1", "t1", 3.0,
            "observer", 4,
        )
        self.assertIsNone(result.materialized)
        self.assertEqual(result.report.accounts_considered, ())
        self.assertEqual(result.belief_states, ())


if __name__ == "__main__":
    unittest.main()
