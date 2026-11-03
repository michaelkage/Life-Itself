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

    def test_reprocessing_answer_is_idempotent_across_all_pipeline_stages(self):
        inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("q-replay", "evt", "alice", "coat", 1),
        ))
        inquiries.append_response(TestimonyResponse("q-replay", 2, True, "green", 0.9))
        testimony = TestimonyLedger((
            TestimonyRecord("t-bob", "evt", "bob", 1, 0.0, 0.0,
                (TestimonyDetail("d-bob", "coat", "black", 0.8),), ()),
        ))
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        pipeline = InquiryInvestigationPipeline()

        first = pipeline.process(
            inquiries, testimony, beliefs, "q-replay", "t-alice", 3.0,
            "observer", 4,
        )
        testimony_after_first = testimony.to_json()
        beliefs_after_first = beliefs.snapshot()

        replay = pipeline.process(
            inquiries, testimony, beliefs, "q-replay", "t-alice", 3.0,
            "observer", 4,
        )

        self.assertEqual(replay.materialized, first.materialized)
        self.assertEqual(replay.report, first.report)
        self.assertEqual(testimony.to_json(), testimony_after_first)
        self.assertEqual(beliefs.to_json(), beliefs_after_first)
        self.assertEqual(len(testimony.snapshot()), 2)
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
