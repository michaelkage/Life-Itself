import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger, SocialInteraction
from simreality.testimony import TestimonyLedger
from simreality.testimony_analysis import TestimonyAnalyzer
from simreality.testimony_beliefs import TestimonyBeliefAdapter
from simreality.witness_recall import RecalledDetail, WitnessRecall


class TestimonyBeliefAdapterTests(unittest.TestCase):
    def make_record(self, testimony_id, witness, value):
        recall = WitnessRecall("evt", witness, 1,
            (RecalledDetail("d-" + witness, "coat", value, 0.8),), ())
        return TestimonyLedger.from_recall(testimony_id, recall, 0.0)

    def test_conflicting_accounts_become_competing_claim_evidence(self):
        ledger = TestimonyLedger((
            self.make_record("t1", "alice", "green"),
            self.make_record("t2", "bob", "black"),
        ))
        report = TestimonyAnalyzer().analyze(ledger, "evt", 2.0)
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        adapter = TestimonyBeliefAdapter()
        states = adapter.apply(beliefs, "observer", report, observed_tick=5)
        self.assertEqual(len(states), 2)
        snapshot = beliefs.beliefs_for("observer")
        self.assertEqual(len(snapshot), 2)
        self.assertTrue(all(state.evidence_ids for state in snapshot))

    def test_replay_is_idempotent(self):
        ledger = TestimonyLedger((
            self.make_record("t1", "alice", "green"),
            self.make_record("t2", "bob", "black"),
        ))
        report = TestimonyAnalyzer().analyze(ledger, "evt", 2.0)
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        adapter = TestimonyBeliefAdapter()
        first = adapter.apply(beliefs, "observer", report, observed_tick=5)
        second = adapter.apply(beliefs, "observer", report, observed_tick=5)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
