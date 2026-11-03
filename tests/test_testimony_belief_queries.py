import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger
from simreality.testimony_belief_queries import TestimonyBeliefQueryAdapter
from simreality.testimony_beliefs import TestimonyBeliefAdapter, TestimonyEvidencePolicy
from simreality.beliefs import Evidence


class TestimonyBeliefQueryTests(unittest.TestCase):
    def test_unknown_claim_stays_unknown_and_query_is_read_only(self):
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        adapter = TestimonyBeliefQueryAdapter()
        result = adapter.query(beliefs, "npc", "event", "coat", "red")
        self.assertFalse(result.known)
        self.assertIsNone(result.confidence)
        self.assertIsNone(result.believes)
        self.assertEqual(beliefs.beliefs_for("npc"), ())

    def test_query_returns_confidence_and_thresholded_opinion(self):
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        evidence = Evidence("e1", "event:evt|coat='red'", "witness", 1, 1.0, 0.5, 1)
        beliefs.observe("npc", evidence)
        result = TestimonyBeliefQueryAdapter().query(
            beliefs, "npc", "evt", "coat", "red"
        )
        self.assertTrue(result.known)
        self.assertEqual(result.confidence, 0.75)
        self.assertTrue(result.believes)

    def test_package_exports_correct_policy_name(self):
        from simreality import TestimonyEvidencePolicy as ExportedPolicy
        self.assertIs(ExportedPolicy, TestimonyEvidencePolicy)


if __name__ == "__main__":
    unittest.main()
