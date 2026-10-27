"""Regression tests for witnessed NPC actions becoming social consequences."""
import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_consequences import (
    ObservedClaim,
    SocialConsequenceRecorder,
    WitnessedSocialEvent,
)
from simreality.social_trust import SocialTrustLedger


class SocialConsequenceTests(unittest.TestCase):
    def setUp(self):
        self.trust = SocialTrustLedger({("witness", "actor"): 0.5})
        self.beliefs = SocialBeliefSystem(self.trust)
        self.recorder = SocialConsequenceRecorder(self.trust, self.beliefs)

    def test_witnessed_action_updates_trust_and_claim_belief(self):
        event = WitnessedSocialEvent(
            "event-1", "witness", "actor", 10, -1, 0.8,
            (ObservedClaim("actor-helped-neighbour", -1, 0.7),),
        )
        result = self.recorder.record(event)
        self.assertAlmostEqual(result.trust_state.trust, 0.1)
        # The claim source is the actor, so the updated low trust affects reliability.
        self.assertAlmostEqual(result.beliefs[0].confidence, 0.4655)

    def test_identical_replay_does_not_apply_consequence_twice(self):
        event = WitnessedSocialEvent("event-2", "witness", "actor", 5, 1, 0.5)
        first = self.recorder.record(event)
        before = self.trust.snapshot()
        second = self.recorder.record(event)
        self.assertEqual(first, second)
        self.assertEqual(self.trust.snapshot(), before)

    def test_conflicting_event_id_rejected(self):
        self.recorder.record(WitnessedSocialEvent("event-3", "witness", "actor", 5, 1, 0.5))
        with self.assertRaises(ValueError):
            self.recorder.record(WitnessedSocialEvent("event-3", "witness", "actor", 5, -1, 0.5))

    def test_claim_order_is_canonical(self):
        event = WitnessedSocialEvent(
            "event-4", "witness", "actor", 3, 1, 0.2,
            (ObservedClaim("z-claim", 1, 0.2), ObservedClaim("a-claim", -1, 0.4)),
        )
        result = self.recorder.record(event)
        self.assertEqual(tuple(state.claim_id for state in result.beliefs), ("a-claim", "z-claim"))

    def test_requires_shared_trust_ledger(self):
        other = SocialBeliefSystem(SocialTrustLedger())
        with self.assertRaises(ValueError):
            SocialConsequenceRecorder(self.trust, other)


if __name__ == "__main__":
    unittest.main()
