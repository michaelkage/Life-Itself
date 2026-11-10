import unittest

from simreality import (
    ChoiceOption, ConditionedDecisionProfile, NPCAppraiser, NPCConditioningLedger,
    NPCValueProfile, PsychologicalDecisionAdapter,
)


class PsychologicalDecisionTests(unittest.TestCase):
    def test_learned_association_changes_consideration_not_world_facts(self):
        ledger = NPCConditioningLedger(associations={("npc", "raised_voice"): -0.9})
        profile = NPCValueProfile("npc", {"justice": 0.5})
        conditioned = ConditionedDecisionProfile("npc", {"raised_voice": 1.0})
        options = [
            ChoiceOption("confront", {"justice": 0.8}),
            ChoiceOption("withdraw", {"justice": 0.2}),
        ]
        result = PsychologicalDecisionAdapter.rank(
            "npc", ledger, profile, conditioned, options,
            cue_exposures={"confront": {"raised_voice": 1.0}},
        )
        self.assertEqual(result.preferred.choice_id, "withdraw")
        self.assertEqual(result.ranked[1].conditioned_contributions,
                         (("raised_voice", -0.9),))

    def test_same_choice_can_rank_differently_for_two_npcs(self):
        options = [ChoiceOption("approach", {"safety": 0.1}),
                   ChoiceOption("avoid", {"safety": 0.0})]
        profile_a = NPCValueProfile("a", {"safety": 0.0})
        profile_b = NPCValueProfile("b", {"safety": 0.0})
        ledger = NPCConditioningLedger(associations={
            ("a", "crowd"): -1.0, ("b", "crowd"): 1.0,
        })
        a = PsychologicalDecisionAdapter.rank(
            "a", ledger, profile_a, ConditionedDecisionProfile("a", {"crowd": 1}),
            options, cue_exposures={"approach": {"crowd": 1}},
        )
        b = PsychologicalDecisionAdapter.rank(
            "b", ledger, profile_b, ConditionedDecisionProfile("b", {"crowd": 1}),
            options, cue_exposures={"approach": {"crowd": 1}},
        )
        self.assertEqual(a.preferred.choice_id, "avoid")
        self.assertEqual(b.preferred.choice_id, "approach")

    def test_conditioning_sensitivity_can_counteract_learned_association(self):
        ledger = NPCConditioningLedger(associations={("npc", "crowd"): -0.8})
        result = PsychologicalDecisionAdapter.rank(
            "npc", ledger, NPCValueProfile("npc", {}),
            ConditionedDecisionProfile("npc", {"crowd": -1}),
            [ChoiceOption("join", {})],
            cue_exposures={"join": {"crowd": 1}},
        )
        self.assertEqual(result.preferred.conditioned_score, 0.8)

    def test_ranking_is_read_only_and_deterministic(self):
        ledger = NPCConditioningLedger(associations={("npc", "cue"): 0.4})
        before = ledger.snapshot()
        args = ("npc", ledger, NPCValueProfile("npc", {}),
                ConditionedDecisionProfile("npc", {"cue": 1}),
                [ChoiceOption("x", {})])
        first = PsychologicalDecisionAdapter.rank(
            *args, cue_exposures={"x": {"cue": 0.5}})
        second = PsychologicalDecisionAdapter.rank(
            *args, cue_exposures={"x": {"cue": 0.5}})
        self.assertEqual(first, second)
        self.assertEqual(before, ledger.snapshot())

    def test_missing_sensitivity_and_unknown_choice_are_rejected(self):
        with self.assertRaises(KeyError):
            PsychologicalDecisionAdapter.rank(
                "npc", NPCConditioningLedger(), NPCValueProfile("npc", {}),
                ConditionedDecisionProfile("npc", {}),
                [ChoiceOption("x", {})], cue_exposures={"x": {"missing": 1}},
            )
        with self.assertRaises(ValueError):
            PsychologicalDecisionAdapter.rank(
                "npc", NPCConditioningLedger(), NPCValueProfile("npc", {}),
                ConditionedDecisionProfile("npc", {}),
                [ChoiceOption("x", {})], cue_exposures={"y": {}},
            )

    def test_profile_owner_must_match(self):
        with self.assertRaises(ValueError):
            PsychologicalDecisionAdapter.rank(
                "npc-a", NPCConditioningLedger(), NPCValueProfile("npc-b", {}),
                ConditionedDecisionProfile("npc-a", {}), [],
                cue_exposures={},
            )


if __name__ == "__main__":
    unittest.main()
