import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger
from simreality.testimony import TestimonyLedger
from simreality.testimony_analysis import TestimonyAnalyzer
from simreality.testimony_followups import TestimonyFollowUpPlanner
from simreality.witness_recall import RecalledDetail, WitnessRecall

class TestimonyFollowUpPlannerTests(unittest.TestCase):
    def make_record(self, tid, witness, value):
        recall = WitnessRecall("evt", witness, 1,
            (RecalledDetail("d-" + witness, "coat", value, 0.8),), ())
        return TestimonyLedger.from_recall(tid, recall, 0.0)

    def test_conflicting_unknown_accounts_produce_deterministic_proposals(self):
        ledger = TestimonyLedger((self.make_record("t1", "alice", "green"),
                                  self.make_record("t2", "bob", "black")))
        report = TestimonyAnalyzer().analyze(ledger, "evt", 2.0)
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        planner = TestimonyFollowUpPlanner()
        first = planner.plan("observer", beliefs, report)
        second = planner.plan("observer", beliefs, report)
        self.assertEqual(first, second)
        self.assertEqual(len(first.proposals), 2)
        self.assertTrue(all(p.priority == p.testimony_confidence for p in first.proposals))
        self.assertEqual(first.proposals[0].priority, first.proposals[1].priority)

    def test_minimum_priority_filters_proposals(self):
        ledger = TestimonyLedger((self.make_record("t1", "alice", "green"),
                                  self.make_record("t2", "bob", "black")))
        report = TestimonyAnalyzer().analyze(ledger, "evt", 2.0)
        plan = TestimonyFollowUpPlanner().plan("observer",
            SocialBeliefSystem(SocialTrustLedger()), report, minimum_priority=0.99)
        self.assertEqual(plan.proposals, ())

if __name__ == "__main__":
    unittest.main()
