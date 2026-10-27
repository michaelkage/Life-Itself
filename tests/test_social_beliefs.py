"""Regression tests for trust-weighted evidence observed by individual NPCs."""
import unittest

from simreality.beliefs import Evidence
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialInteraction, SocialTrustLedger


class SocialBeliefSystemTests(unittest.TestCase):
    def evidence(self, eid="report", direction=1, source="witness", tick=1, strength=1.0, reliability=1.0, claim="saw-event"):
        return Evidence(eid, claim, source, direction, strength, reliability, tick)

    def test_same_report_changes_beliefs_differently_by_observer_trust(self):
        trust = SocialTrustLedger({("skeptic", "witness"): 0.1, ("supporter", "witness"): 0.9})
        system = SocialBeliefSystem(trust)
        skeptic = system.observe("skeptic", self.evidence())
        supporter = system.observe("supporter", self.evidence())
        self.assertAlmostEqual(skeptic.confidence, 0.55)
        self.assertAlmostEqual(supporter.confidence, 0.95)

    def test_unknown_source_uses_neutral_fallback(self):
        system = SocialBeliefSystem(SocialTrustLedger())
        state = system.observe("observer", self.evidence())
        self.assertAlmostEqual(state.confidence, 0.75)

    def test_incoming_reliability_is_overridden_by_observer_trust(self):
        trust = SocialTrustLedger({("observer", "witness"): 0.2})
        system = SocialBeliefSystem(trust)
        state = system.observe("observer", self.evidence(reliability=1.0))
        self.assertAlmostEqual(state.confidence, 0.6)

    def test_trust_is_sampled_at_observation_time(self):
        trust = SocialTrustLedger({("observer", "witness"): 0.2})
        system = SocialBeliefSystem(trust)
        first = system.observe("observer", self.evidence("first"))
        trust.add(SocialInteraction("later-help", "observer", "witness", 1, 1.0, 2))
        self.assertEqual(system.get("observer", "saw-event"), first)
        second = system.observe("observer", self.evidence("second", tick=3))
        self.assertGreater(second.confidence, first.confidence)

    def test_replay_is_idempotent_and_conflicting_id_rejected(self):
        system = SocialBeliefSystem(SocialTrustLedger({("observer", "witness"): 0.7}))
        item = self.evidence()
        self.assertEqual(system.observe("observer", item), system.observe("observer", item))
        with self.assertRaises(ValueError):
            system.observe("observer", self.evidence(direction=-1))

    def test_observers_have_independent_belief_ledgers(self):
        system = SocialBeliefSystem(SocialTrustLedger())
        system.observe("alice", self.evidence(direction=1))
        system.observe("bob", self.evidence(direction=-1))
        self.assertGreater(system.get("alice", "saw-event").confidence, 0.5)
        self.assertLess(system.get("bob", "saw-event").confidence, 0.5)

    def test_snapshots_are_stably_sorted(self):
        system = SocialBeliefSystem(SocialTrustLedger())
        system.observe("z", self.evidence("z-report", claim="z-claim"))
        system.observe("a", self.evidence("a-report", direction=-1, claim="a-claim"))
        self.assertEqual([(owner, state.claim_id) for owner, state in system.snapshot()], [("a", "a-claim"), ("z", "z-claim")])


if __name__ == "__main__":
    unittest.main()
