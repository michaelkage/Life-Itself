"""Tests for deterministic, non-moralizing NPC choice appraisal."""
import unittest

from simreality.appraisal import ChoiceOption, NPCAppraiser, NPCValueProfile


class NPCAppraiserTests(unittest.TestCase):
    def test_same_options_can_rank_differently_for_different_npcs(self):
        options = [
            ChoiceOption("protect-friend", {"loyalty": 1, "security": -0.5}),
            ChoiceOption("report-friend", {"loyalty": -0.5, "security": 1}),
        ]
        loyal = NPCValueProfile("loyal", {"loyalty": 1, "security": 0.2})
        cautious = NPCValueProfile("cautious", {"loyalty": 0.1, "security": 1})
        self.assertEqual(NPCAppraiser.rank(loyal, options)[0].choice_id, "protect-friend")
        self.assertEqual(NPCAppraiser.rank(cautious, options)[0].choice_id, "report-friend")

    def test_bias_cues_change_appraisal_without_global_moral_labels(self):
        profile = NPCValueProfile("npc", {"fairness": 0.2}, {"authority": 1.0})
        options = [
            ChoiceOption("challenge", {"fairness": 1}, {"authority": -1}),
            ChoiceOption("comply", {"fairness": -0.2}, {"authority": 1}),
        ]
        ranked = NPCAppraiser.rank(profile, options)
        self.assertEqual(ranked[0].choice_id, "comply")
        self.assertEqual(ranked[0].bias_contributions, (("authority", 1.0),))

    def test_missing_dimensions_are_neutral_and_results_are_deterministic(self):
        profile = NPCValueProfile("npc", {"care": 1})
        options = [ChoiceOption("z", {}), ChoiceOption("a", {})]
        expected = NPCAppraiser.rank(profile, options)
        self.assertEqual([r.choice_id for r in expected], ["a", "z"])
        self.assertEqual(expected, NPCAppraiser.rank(profile, options))
        self.assertEqual(expected[0].score, 0.0)

    def test_contributions_are_explained_in_stable_axis_order(self):
        profile = NPCValueProfile("npc", {"security": 0.5, "loyalty": 1})
        option = ChoiceOption("choice", {"security": 1, "loyalty": -0.5})
        result = NPCAppraiser.appraise(profile, option)
        self.assertEqual(result.value_contributions, (("loyalty", -0.5), ("security", 0.5)))
        self.assertEqual(result.score, 0.0)

    def test_duplicate_choice_ids_are_rejected(self):
        profile = NPCValueProfile("npc", {})
        options = [ChoiceOption("same", {}), ChoiceOption("same", {})]
        with self.assertRaises(ValueError):
            NPCAppraiser.rank(profile, options)

    def test_invalid_numeric_values_are_rejected(self):
        with self.assertRaises(ValueError):
            NPCValueProfile("npc", {"security": float("nan")})
        with self.assertRaises(ValueError):
            ChoiceOption("choice", {"care": 1.5})
        with self.assertRaises(ValueError):
            NPCValueProfile("npc", {"care": True})


if __name__ == "__main__":
    unittest.main()
