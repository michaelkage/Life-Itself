import unittest

from simreality.identity_context import NPCEmotionalState
from simreality.emotional_regulation import (
    EmotionalDecisionAdapter, EmotionalDecisionRule,
    EmotionalExpressionAdapter, EmotionalRegulationProfile,
)


class EmotionalRegulationTests(unittest.TestCase):
    def test_suppression_changes_expression_not_felt_emotion(self):
        state = NPCEmotionalState("npc-a", 12, {"anger": 0.8, "affection": 0.6})
        profile = EmotionalRegulationProfile("npc-a", {"anger": 0.75})
        expression = EmotionalExpressionAdapter.project(state, profile)
        self.assertEqual(expression.felt_for("anger"), 0.8)
        self.assertAlmostEqual(expression.displayed_for("anger"), 0.2)
        self.assertAlmostEqual(expression.concealed_for("anger"), 0.6)
        self.assertEqual(expression.displayed_for("affection"), 0.6)
        self.assertEqual(state.intensities["anger"], 0.8)

    def test_conflicting_emotions_can_be_felt_and_expressed_together(self):
        state = NPCEmotionalState("npc-a", 2, {"affection": 0.7, "resentment": 0.8})
        profile = EmotionalRegulationProfile("npc-a", {"resentment": 0.5})
        expression = EmotionalExpressionAdapter.project(state, profile)
        self.assertEqual(expression.felt_for("affection"), 0.7)
        self.assertEqual(expression.felt_for("resentment"), 0.8)
        self.assertEqual(expression.displayed_for("affection"), 0.7)
        self.assertEqual(expression.displayed_for("resentment"), 0.4)

    def test_decision_influence_is_explicit_and_does_not_choose_action(self):
        state = NPCEmotionalState("npc-a", 5, {"fear": 0.8, "pride": 0.5})
        result = EmotionalDecisionAdapter.assess(
            state, "confrontation", baseline=0.4,
            rules=(
                EmotionalDecisionRule("confrontation", "fear", -0.5),
                EmotionalDecisionRule("confrontation", "pride", 0.2),
            ),
        )
        self.assertAlmostEqual(result.emotional_delta, -0.3)
        self.assertAlmostEqual(result.adjusted_score, 0.1)
        self.assertEqual(dict(result.contributions), {"fear": -0.4, "pride": 0.1})

    def test_decision_scores_are_bounded_and_profile_ownership_is_enforced(self):
        state = NPCEmotionalState("npc-a", 1, {"anger": 1.0})
        result = EmotionalDecisionAdapter.assess(
            state, "retaliate", baseline=0.9,
            rules=(EmotionalDecisionRule("retaliate", "anger", 1.0),),
        )
        self.assertEqual(result.adjusted_score, 1.0)
        with self.assertRaisesRegex(ValueError, "owner"):
            EmotionalExpressionAdapter.project(
                state, EmotionalRegulationProfile("npc-b", {}),
            )

    def test_invalid_rules_and_suppression_are_rejected(self):
        with self.assertRaises(ValueError):
            EmotionalRegulationProfile("npc-a", {"anger": 1.2})
        with self.assertRaises(ValueError):
            EmotionalDecisionRule("fight", "anger", float("nan"))


if __name__ == "__main__":
    unittest.main()
