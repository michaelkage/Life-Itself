import unittest

from simreality import (
    BeliefLedger, BeliefLedgerSnapshot, Evidence, SocialBeliefSnapshot,
    SocialBeliefSystem, SocialInteraction, SocialTrustLedger,
)


class BeliefPersistenceTests(unittest.TestCase):
    def test_ledger_round_trip_preserves_priors_and_evidence_history(self):
        ledger = BeliefLedger({"claim:case-1": 0.2, "claim:case-2": 0.8})
        ledger.add(Evidence("e2", "claim:case-1", "witness-b", -1, 0.4, 0.6, 5))
        ledger.add(Evidence("e1", "claim:case-1", "witness-a", 1, 0.8, 0.7, 2))
        snapshot = BeliefLedgerSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = BeliefLedgerSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(BeliefLedgerSnapshot.capture(restored).to_json(), payload)

    def test_social_beliefs_preserve_sampled_reliability_and_replay_inputs(self):
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        original_input = Evidence("report-1", "claim:incident", "speaker", 1, 0.7, 0.1, 10)
        beliefs.observe("listener", original_input)
        # Later trust changes must not rewrite reliability sampled at observation time.
        trust.add(SocialInteraction("later", "listener", "speaker", -1, 1.0, 11, "betrayal"))
        snapshot = SocialBeliefSnapshot.capture(beliefs)
        payload = snapshot.to_json()
        restored = SocialBeliefSnapshot.from_json(payload).restore(trust)
        self.assertEqual(restored.snapshot(), beliefs.snapshot())
        self.assertEqual(restored.observe("listener", original_input), beliefs.get("listener", "claim:incident"))
        self.assertEqual(SocialBeliefSnapshot.capture(restored).to_json(), payload)

    def test_observers_remain_independent_and_unknown_schema_rejected(self):
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        beliefs.observe("a", Evidence("e", "claim", "source", 1, 1.0, 0.5, 1))
        payload = SocialBeliefSnapshot.capture(beliefs).to_json()
        restored = SocialBeliefSnapshot.from_json(payload).restore(trust)
        self.assertEqual(restored.beliefs_for("a"), beliefs.beliefs_for("a"))
        with self.assertRaises(ValueError):
            SocialBeliefSnapshot.from_json('{"schema_version":99}')
        with self.assertRaises(ValueError):
            BeliefLedgerSnapshot.from_json('{"schema_version":99}')


if __name__ == "__main__":
    unittest.main()
