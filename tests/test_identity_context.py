import unittest

from simreality.identity_evolution import IdentityChangeProposal
from simreality.identity_interpretation import IdentityBeliefInterpreter
from simreality.identity_context import (
    IdentityCognitiveBiasRule, IdentityEmotionRule, IdentityCognitiveContextInterpreter,
    NPCCognitiveBiasProfile, NPCEmotionalState,
)


class IdentityCognitiveContextTests(unittest.TestCase):
    def setUp(self):
        self.interpreter = IdentityCognitiveContextInterpreter(IdentityBeliefInterpreter(()))
        self.proposal = IdentityChangeProposal(
            "event-1", "npc-a", "conflict-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "witness", 0.05,
        )

    def test_bias_and_temporary_emotion_are_separate_contributions(self):
        result = self.interpreter.interpret(
            (self.proposal,),
            biases_by_npc={"npc-a": NPCCognitiveBiasProfile("npc-a", {"confirmation": 0.8})},
            bias_rules=(IdentityCognitiveBiasRule("conflict-policy", "confirmation", 0.01),),
            emotions_by_npc={"npc-a": NPCEmotionalState("npc-a", 12, {"fear": 0.9, "anger": 0.2})},
            emotion_rules=(IdentityEmotionRule("conflict-policy", "fear", 0.02),),
            current_tick=12,
            max_emotion_age_ticks=2,
        )[0]
        self.assertAlmostEqual(result.bias_contributions[0][2], 0.008)
        self.assertAlmostEqual(result.emotion_contributions[0][2], 0.018)
        self.assertAlmostEqual(result.interpreted.delta, 0.046)
        self.assertEqual(result.emotional_sample_tick, 12)
        self.assertAlmostEqual(result.base.interpreted.delta, self.proposal.delta)

    def test_emotional_state_is_immutable_and_missing_axes_are_neutral(self):
        state = NPCEmotionalState("npc-a", 5, {"grief": 0.7})
        with self.assertRaises(TypeError):
            state.intensities["grief"] = 0.0
        result = self.interpreter.interpret(
            (self.proposal,), emotions_by_npc={"npc-a": state},
            emotion_rules=(IdentityEmotionRule("conflict-policy", "stress", 0.04),),
        )[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertEqual(result.emotion_contributions[0][1], 0.0)

    def test_stale_and_future_emotion_snapshots_are_rejected(self):
        state = NPCEmotionalState("npc-a", 2, {"fear": 0.8})
        args = dict(emotions_by_npc={"npc-a": state},
                    emotion_rules=(IdentityEmotionRule("conflict-policy", "fear", 0.02),))
        with self.assertRaises(ValueError):
            self.interpreter.interpret((self.proposal,), **args, current_tick=8, max_emotion_age_ticks=3)
        with self.assertRaises(ValueError):
            self.interpreter.interpret((self.proposal,), **args, current_tick=1)

    def test_invalid_axes_and_duplicate_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            NPCCognitiveBiasProfile("npc-a", {"negativity": 1.2})
        with self.assertRaises(ValueError):
            NPCEmotionalState("npc-a", 1, {"anger": float("nan")})
        rule = IdentityCognitiveBiasRule("conflict-policy", "negativity", 0.1)
        with self.assertRaises(ValueError):
            self.interpreter.interpret((self.proposal,), bias_rules=(rule, rule))


if __name__ == "__main__":
    unittest.main()
