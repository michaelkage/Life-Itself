import unittest

from simreality import (
    CopingProfile, NPCStressLedger, StressAdaptationProfile,
    StressBehaviorAdapter,
)


class StressBehaviorAdaptationTests(unittest.TestCase):
    def test_same_stress_can_produce_different_individual_responses(self):
        ledger = NPCStressLedger(initial_stress={"withdrawn": 0.8, "driven": 0.8})
        coping_a = CopingProfile("withdrawn", exhaustion_threshold=0.5, breaking_point=1.0)
        coping_b = CopingProfile("driven", exhaustion_threshold=0.5, breaking_point=1.0)
        withdrawn = StressBehaviorAdapter.assess(
            ledger, coping_a,
            StressAdaptationProfile("withdrawn", {"social_engagement": -0.8},
                                   {"social_engagement": -0.6}),
        )
        driven = StressBehaviorAdapter.assess(
            ledger, coping_b,
            StressAdaptationProfile("driven", {"social_engagement": 0.2, "work_performance": 0.5},
                                   {"social_engagement": 0.1, "work_performance": -0.2}),
        )
        self.assertLess(withdrawn.modifier_for("social_engagement"), 0)
        self.assertGreater(driven.modifier_for("social_engagement"), 0)
        self.assertNotEqual(withdrawn.modifiers, driven.modifiers)

    def test_exhaustion_is_separate_from_general_stress(self):
        ledger = NPCStressLedger(initial_stress={"npc": 0.8})
        coping = CopingProfile("npc", exhaustion_threshold=0.5, breaking_point=1.0)
        result = StressBehaviorAdapter.assess(
            ledger, coping,
            StressAdaptationProfile("npc", {"work_performance": -0.1},
                                    {"work_performance": -0.9}),
        )
        self.assertAlmostEqual(result.modifier_for("work_performance"), -0.64)

    def test_outputs_are_bounded_and_all_channels_are_explicit(self):
        ledger = NPCStressLedger(initial_stress={"npc": 1.0})
        coping = CopingProfile("npc", exhaustion_threshold=0.5, breaking_point=1.0)
        result = StressBehaviorAdapter.assess(
            ledger, coping,
            StressAdaptationProfile("npc", {"risk_tolerance": -1.0},
                                    {"risk_tolerance": -1.0}),
        )
        self.assertEqual(len(result.modifiers), 6)
        self.assertEqual(result.modifier_for("risk_tolerance"), -1.0)
        self.assertEqual(result.sampled_tick, 0)

    def test_assessment_does_not_mutate_stress_history(self):
        ledger = NPCStressLedger(initial_stress={"npc": 0.7})
        before = ledger.snapshot()
        coping = CopingProfile("npc")
        StressBehaviorAdapter.assess(
            ledger, coping,
            StressAdaptationProfile("npc", {"sleep_priority": 0.5}, {}),
        )
        self.assertEqual(ledger.snapshot(), before)

    def test_profiles_must_belong_to_same_npc(self):
        with self.assertRaises(ValueError):
            StressBehaviorAdapter.assess(
                NPCStressLedger(), CopingProfile("a"),
                StressAdaptationProfile("b", {}, {}),
            )

    def test_unknown_channel_and_out_of_range_coefficients_rejected(self):
        with self.assertRaises(ValueError):
            StressAdaptationProfile("npc", {"aggression": 1.0}, {})
        with self.assertRaises(ValueError):
            StressAdaptationProfile("npc", {"social_engagement": 1.5}, {})


if __name__ == "__main__":
    unittest.main()
