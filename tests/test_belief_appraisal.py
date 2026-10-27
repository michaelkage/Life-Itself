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

    def test_new_evidence_changes_choice_ranking(self):
        profile = NPCValueProfile("npc", {"security": 1.0})
        beliefs = BeliefLedger({"claim": 0.5})
        options = [ChoiceOption("act", {}), ChoiceOption("wait", {"security": 0.2})]
        effects = {"claim": {"security": 0.8}}
        self.assertEqual(BeliefAwareAppraiser.rank(profile, options, beliefs, value_effects=effects)[0].choice_id, "wait")
        beliefs.add(Evidence("e1", "claim", "witness", 1, 1.0, 1.0, 1))
        self.assertEqual(BeliefAwareAppraiser.rank(profile, options, beliefs, value_effects=effects)[0].choice_id, "act")

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
