import unittest

from simreality.appraisal import ChoiceOption, NPCValueProfile
from simreality.beliefs import Evidence
from simreality.psychological_conditioning import NPCConditioningLedger
from simreality.psychological_decisions import ConditionedDecisionProfile
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger
from simreality.integrated_decisions import IntegratedPsychologicalDecisionAdapter


class IntegratedPsychologicalDecisionTests(unittest.TestCase):
    def test_beliefs_and_learned_associations_both_contribute(self):
        trust = SocialTrustLedger({("npc", "witness"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        beliefs.observe("npc", Evidence("e1", "guard-is-corrupt", "witness", 1, 1.0, 1.0, 1))
        conditioning = NPCConditioningLedger(associations={("npc", "authority"): -0.8})
        profile = NPCValueProfile("npc", {"justice": 0.5})
        options = [
            ChoiceOption("report", {"justice": 0.2}),
            ChoiceOption("stay_silent", {"justice": 0.0}),
        ]
        result = IntegratedPsychologicalDecisionAdapter.rank(
            "npc", beliefs, conditioning, profile,
            ConditionedDecisionProfile("npc", {"authority": 1.0}),
            options,
            value_effects={"guard-is-corrupt": {"justice": 0.8}},
            cue_exposures={"report": {"authority": 1.0}},
        )
        report = next(item for item in result.ranked if item.choice_id == "report")
        self.assertEqual(report.conditioned_contributions, (("authority", -0.8),))
        self.assertAlmostEqual(report.final_score, report.belief_appraisal.score - 0.8)
        self.assertEqual(result.preferred.choice_id, "stay_silent")

    def test_same_choices_can_rank_differently_for_two_npcs(self):
        trust = SocialTrustLedger({
            ("a", "source"): 0.9,
            ("b", "source"): 0.1,
        })
        beliefs = SocialBeliefSystem(trust)
        evidence = Evidence("e1", "crowds-are-safe", "source", 1, 1.0, 1.0, 1)
        beliefs.observe("a", evidence)
        beliefs.observe("b", evidence)
        conditioning = NPCConditioningLedger(associations={
            ("a", "crowd"): 0.8, ("b", "crowd"): -0.8,
        })
        options = [ChoiceOption("join", {"safety": 0.0}),
                   ChoiceOption("avoid", {"safety": 0.0})]
        kwargs = dict(
            beliefs=beliefs, conditioning=conditioning,
            value_profile=NPCValueProfile("a", {"safety": 0.0}),
            conditioning_profile=ConditionedDecisionProfile("a", {"crowd": 1.0}),
            options=options, cue_exposures={"join": {"crowd": 1.0}},
        )
        a = IntegratedPsychologicalDecisionAdapter.rank("a", **kwargs)
        b = IntegratedPsychologicalDecisionAdapter.rank(
            "b", beliefs, conditioning, NPCValueProfile("b", {"safety": 0.0}),
            ConditionedDecisionProfile("b", {"crowd": 1.0}), options,
            cue_exposures={"join": {"crowd": 1.0}},
        )
        self.assertEqual(a.preferred.choice_id, "join")
        self.assertEqual(b.preferred.choice_id, "avoid")

    def test_read_only_deterministic_and_unknown_choice_rejected(self):
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        conditioning = NPCConditioningLedger(associations={("npc", "cue"): 0.5})
        before_beliefs = beliefs.snapshot()
        before_conditioning = conditioning.snapshot()
        args = (
            "npc", beliefs, conditioning, NPCValueProfile("npc", {}),
            ConditionedDecisionProfile("npc", {"cue": 1.0}),
            [ChoiceOption("x", {})],
        )
        first = IntegratedPsychologicalDecisionAdapter.rank(
            *args, cue_exposures={"x": {"cue": 0.5}},
        )
        second = IntegratedPsychologicalDecisionAdapter.rank(
            *args, cue_exposures={"x": {"cue": 0.5}},
        )
        self.assertEqual(first, second)
        self.assertEqual(beliefs.snapshot(), before_beliefs)
        self.assertEqual(conditioning.snapshot(), before_conditioning)
        with self.assertRaises(ValueError):
            IntegratedPsychologicalDecisionAdapter.rank(
                *args, cue_exposures={"unknown": {}},
            )


    def test_recalled_memories_can_influence_integrated_choices_without_forcing_them(self):
        from simreality.npc_life_history import AutobiographicalMemory
        from simreality.npc_memory_recall import MemoryRecallResult, RecalledMemory
        from simreality.memory_decisions import (
            MemoryChoiceAssociation, MemoryDecisionInfluenceAdapter, MemoryDecisionProfile,
        )
        memory = AutobiographicalMemory(
            "m1", "npc", "e1", 1, (), "A threatening encounter", 0.8, 0.0,
        )
        recalled = MemoryRecallResult("npc", 2, (
            RecalledMemory(memory, 0.9, ("crowd",), ("crowd-memory",)),
        ))
        influence = MemoryDecisionInfluenceAdapter.evaluate(
            MemoryDecisionProfile("npc", (
                MemoryChoiceAssociation("a1", "npc", "enter", "enter_crowd", -0.8),
            )),
            recalled,
        )
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        conditioning = NPCConditioningLedger()
        options = [ChoiceOption("enter_crowd", {}), ChoiceOption("stay_home", {})]
        result = IntegratedPsychologicalDecisionAdapter.rank(
            "npc", beliefs, conditioning, NPCValueProfile("npc", {}),
            ConditionedDecisionProfile("npc", {}), options,
            cue_exposures={}, memory_influence=influence,
        )
        self.assertEqual(result.preferred.choice_id, "stay_home")
        enter = next(item for item in result.ranked if item.choice_id == "enter_crowd")
        self.assertEqual(enter.memory_contributions, (("m1", -0.72),))
        self.assertEqual(enter.final_score, -0.72)

    def test_memory_influence_from_another_npc_is_rejected(self):
        from simreality.memory_decisions import MemoryDecisionInfluence
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        with self.assertRaises(ValueError):
            IntegratedPsychologicalDecisionAdapter.rank(
                "npc", beliefs, NPCConditioningLedger(), NPCValueProfile("npc", {}),
                ConditionedDecisionProfile("npc", {}), [ChoiceOption("x", {})],
                cue_exposures={}, memory_influence=MemoryDecisionInfluence("other", 0, ()),
            )


if __name__ == "__main__":
    unittest.main()
