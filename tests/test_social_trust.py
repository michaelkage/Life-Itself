"""Tests for deterministic observer-specific NPC trust."""
import unittest
from simreality.social_trust import SocialInteraction, SocialTrustLedger

class SocialTrustTests(unittest.TestCase):
    def event(self, eid, direction, tick=1, strength=1.0, observer="alice", target="bob"):
        return SocialInteraction(eid, observer, target, direction, strength, tick)

    def test_trust_is_observer_specific(self):
        ledger = SocialTrustLedger()
        ledger.add(self.event("a-trusts-b", 1, observer="alice", target="bob"))
        ledger.add(self.event("c-distrusts-b", -1, observer="carol", target="bob"))
        self.assertEqual(ledger.get("alice", "bob").trust, 1.0)
        self.assertEqual(ledger.get("carol", "bob").trust, 0.0)

    def test_prior_and_interaction_strength(self):
        ledger = SocialTrustLedger({("alice", "bob"): 0.2})
        state = ledger.add(self.event("small-kindness", 1, strength=0.5))
        self.assertAlmostEqual(state.trust, 0.6)

    def test_replay_is_order_independent_and_stable(self):
        events = [self.event("later-betrayal", -1, tick=3, strength=0.4), self.event("early-help", 1, tick=1, strength=0.6)]
        a, b = SocialTrustLedger(), SocialTrustLedger()
        a.add_many(events)
        b.add_many(reversed(events))
        self.assertEqual(a.snapshot(), b.snapshot())

    def test_duplicate_is_idempotent_and_conflict_rejected(self):
        ledger = SocialTrustLedger()
        event = self.event("same", 1)
        self.assertEqual(ledger.add(event), ledger.add(event))
        with self.assertRaises(ValueError):
            ledger.add(self.event("same", -1))

    def test_trust_can_be_used_as_source_reliability(self):
        ledger = SocialTrustLedger({("alice", "witness"): 0.8})
        self.assertEqual(ledger.get("alice", "witness").source_reliability, 0.8)

    def test_invalid_events_rejected(self):
        with self.assertRaises(ValueError):
            SocialInteraction("e", "a", "a", 1, 0.5, 1)
        with self.assertRaises(ValueError):
            SocialInteraction("e", "a", "b", 0, 0.5, 1)
        with self.assertRaises(ValueError):
            SocialInteraction("e", "a", "b", 1, 1.5, 1)

if __name__ == "__main__":
    unittest.main()
