"""Tests for per-witness interpretation of authoritative world events."""
import unittest

from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_consequences import ObservedClaim, SocialConsequenceRecorder
from simreality.social_trust import SocialTrustLedger
from simreality.world_events import WorldEventLedger
from simreality.world_event_social import WorldEventSocialAdapter


class WorldEventSocialAdapterTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "market-incident", 12, "argument",
                participants=("shopkeeper", "resident"),
                witnesses=("witness-a", "witness-b"),
            ),
        ))
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        recorder = SocialConsequenceRecorder(trust, beliefs)
        self.adapter = WorldEventSocialAdapter(self.events, recorder)
        self.trust = trust
        self.beliefs = beliefs

    def test_witnesses_can_interpret_same_event_differently(self):
        first = self.adapter.record_interpretation(
            "market-incident", "witness-a", "resident", -1, 0.8,
            (ObservedClaim("resident-threatened-shopkeeper", 1, 0.9),),
        )
        second = self.adapter.record_interpretation(
            "market-incident", "witness-b", "resident", 1, 0.6,
            (ObservedClaim("resident-threatened-shopkeeper", -1, 0.7),),
        )
        self.assertLess(first.trust_state.trust, 0.5)
        self.assertGreater(second.trust_state.trust, 0.5)
        self.assertGreater(
            self.beliefs.get("witness-a", "resident-threatened-shopkeeper").confidence,
            self.beliefs.get("witness-b", "resident-threatened-shopkeeper").confidence,
        )

    def test_interpretation_uses_authoritative_event_tick(self):
        result = self.adapter.record_interpretation(
            "market-incident", "witness-a", "resident", 1, 0.5
        )
        self.assertEqual(result.trust_state.last_updated_tick, 12)

    def test_non_witness_cannot_submit_witness_interpretation(self):
        with self.assertRaises(ValueError):
            self.adapter.record_interpretation(
                "market-incident", "stranger", "resident", 1, 0.5
            )

    def test_actor_must_be_event_participant(self):
        with self.assertRaises(ValueError):
            self.adapter.record_interpretation(
                "market-incident", "witness-a", "stranger", 1, 0.5
            )

    def test_replay_is_idempotent(self):
        args = ("market-incident", "witness-a", "resident", -1, 0.8)
        first = self.adapter.record_interpretation(*args)
        second = self.adapter.record_interpretation(*args)
        self.assertEqual(first, second)
        self.assertEqual(len(self.trust.get("witness-a", "resident").interaction_ids), 1)


if __name__ == "__main__":
    unittest.main()
