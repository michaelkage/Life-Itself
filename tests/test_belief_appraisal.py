"""Tests for belief-aware NPC appraisal."""
import unittest
from simreality.appraisal import ChoiceOption, NPCValueProfile
from simreality.beliefs import BeliefLedger, Evidence
from simreality.belief_appraisal import BeliefAwareAppraiser

class Tests(unittest.TestCase):
    def test_confidence_changes_score(self):
        profile = NPCValueProfile("npc", {"security": 1.0})
        option = ChoiceOption("report", {"security": 0.0})
        effects = {"claim": {"security": 0.8}}
        high = BeliefAwareAppraiser.appraise(profile, option, BeliefLedger({"claim": 1.0}), value_effects=effects)
        low = BeliefAwareAppraiser.appraise(profile, option, BeliefLedger({"claim": 0.0}), value_effects=effects)
        self.assertAlmostEqual(high.score, 0.8)
        self.assertAlmostEqual(low.score, -0.8)
        self.assertEqual(high.belief_value_contributions, (("claim", "security", 0.8),))

    def test_neutral_prior_has_no_effect(self):
        result = BeliefAwareAppraiser.appraise(NPCValueProfile("npc", {"security": 1.0}), ChoiceOption("x", {}), BeliefLedger({"claim": 0.5}), value_effects={"claim": {"security": 0.8}})
        self.assertEqual(result.score, 0.0)

    def test_new_evidence_updates_scores_without_claim_specific_choice_mapping(self):
        profile = NPCValueProfile("npc", {"security": 1.0})
        beliefs = BeliefLedger({"claim": 0.5})
        options = [ChoiceOption("act", {}), ChoiceOption("wait", {"security": 0.2})]
        effects = {"claim": {"security": 0.8}}
        before = BeliefAwareAppraiser.rank(profile, options, beliefs, value_effects=effects)
        self.assertEqual(before[0].choice_id, "wait")
        before_act_score = next(item.score for item in before if item.choice_id == "act")
        beliefs.add(Evidence("e1", "claim", "witness", 1, 1.0, 1.0, 1))
        after = BeliefAwareAppraiser.rank(profile, options, beliefs, value_effects=effects)
        self.assertEqual(after[0].choice_id, "wait")
        after_act_score = next(item.score for item in after if item.choice_id == "act")
        self.assertGreater(after_act_score, before_act_score)

    def test_adjustments_saturate_at_valid_impact_bounds(self):
        profile = NPCValueProfile("npc", {"security": 1.0})
        option = ChoiceOption("x", {"security": 0.9})
        result = BeliefAwareAppraiser.appraise(profile, option, BeliefLedger({"claim": 1.0}), value_effects={"claim": {"security": 0.8}})
        self.assertEqual(result.score, 1.0)
        self.assertAlmostEqual(result.belief_value_contributions[0][2], 0.1)

    def test_bias_effects_are_explained(self):
        profile = NPCValueProfile("npc", {}, {"authority": 1.0})
        result = BeliefAwareAppraiser.appraise(profile, ChoiceOption("x", {}), BeliefLedger({"claim": 1.0}), bias_effects={"claim": {"authority": 0.4}})
        self.assertAlmostEqual(result.score, 0.4)
        self.assertEqual(result.belief_bias_contributions, (("claim", "authority", 0.4),))

    def test_invalid_coefficient_and_unknown_claim_rejected(self):
        profile = NPCValueProfile("npc", {})
        with self.assertRaises(ValueError):
            BeliefAwareAppraiser.appraise(profile, ChoiceOption("x", {}), BeliefLedger({"claim": 0.5}), value_effects={"claim": {"security": 2.0}})
        with self.assertRaises(KeyError):
            BeliefAwareAppraiser.appraise(profile, ChoiceOption("x", {}), BeliefLedger(), value_effects={"missing": {"security": 0.2}})

if __name__ == "__main__":
    unittest.main()
