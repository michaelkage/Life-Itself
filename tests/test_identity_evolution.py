"""Tests for gradual, individual-specific NPC identity proposals."""
import unittest

from simreality.identity_evolution import (
    IdentityChangePolicy, IdentityEvolutionEvaluator, NPCIdentityProfile,
)
from simreality.world_events import WorldEventLedger


class IdentityEvolutionTests(unittest.TestCase):
    def test_same_event_can_change_profiles_differently(self):
        profiles = (
            NPCIdentityProfile("cautious", {"trust": 0.2}, {"trust": 0.5}),
            NPCIdentityProfile("open", {"trust": 0.2}, {"trust": 2.0}),
        )
        policy = IdentityChangePolicy(
            "betrayal", "betrayal_discovered", "trust", -0.08,
            "evidence_strength", 0.5, 0.05,
        )
        event = WorldEventLedger.make_event(
            "event-1", 4, "betrayal_discovered",
            participants=("cautious", "open"),
            attributes={"evidence_strength": 0.8},
        )
        result = IdentityEvolutionEvaluator(profiles, (policy,)).assess((event,))
        self.assertEqual([p.npc_id for p in result], ["cautious", "open"])
        self.assertAlmostEqual(result[0].delta, -0.032)
        self.assertAlmostEqual(result[1].delta, -0.05)
        self.assertEqual(profiles[0].traits["trust"], 0.2)

    def test_witness_can_be_included_or_excluded(self):
        profile = NPCIdentityProfile("observer", {"trust": 0.4})
        event = WorldEventLedger.make_event(
            "event-2", 5, "incident", witnesses=("observer",)
        )
        included = IdentityChangePolicy("include", "incident", "trust", 0.02)
        excluded = IdentityChangePolicy(
            "exclude", "incident", "trust", 0.02, include_witnesses=False
        )
        self.assertEqual(
            IdentityEvolutionEvaluator((profile,), (included,)).assess((event,))[0].role,
            "witness",
        )
        self.assertEqual(
            IdentityEvolutionEvaluator((profile,), (excluded,)).assess((event,)), ()
        )

    def test_strength_threshold_and_bounds(self):
        profile = NPCIdentityProfile("npc", {"trust": -0.99}, {"trust": 2.0})
        policy = IdentityChangePolicy(
            "policy", "incident", "trust", -1.0,
            "strength", 0.8, 0.04,
        )
        weak = WorldEventLedger.make_event(
            "weak", 1, "incident", participants=("npc",),
            attributes={"strength": 0.4},
        )
        strong = WorldEventLedger.make_event(
            "strong", 2, "incident", participants=("npc",),
            attributes={"strength": 1.0},
        )
        result = IdentityEvolutionEvaluator((profile,), (policy,)).assess((weak, strong))
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].delta, -0.01)
        self.assertEqual(result[0].after, -1.0)

    def test_stable_order_and_duplicate_event_rejection(self):
        profile = NPCIdentityProfile("npc", {"curiosity": 0.0})
        policy = IdentityChangePolicy("policy", "discovery", "curiosity", 0.03)
        first = WorldEventLedger.make_event(
            "b", 2, "discovery", participants=("npc",)
        )
        second = WorldEventLedger.make_event(
            "a", 1, "discovery", participants=("npc",)
        )
        evaluator = IdentityEvolutionEvaluator((profile,), (policy,))
        self.assertEqual(evaluator.assess((first, second)), evaluator.assess((second, first)))
        with self.assertRaises(ValueError):
            evaluator.assess((first, first))

    def test_invalid_traits_are_rejected(self):
        with self.assertRaises(ValueError):
            NPCIdentityProfile("npc", {"trust": 1.1})
        with self.assertRaises(ValueError):
            NPCIdentityProfile("npc", {"trust": 0.2}, {"trust": 2.1})


if __name__ == "__main__":
    unittest.main()
