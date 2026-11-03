import unittest

from simreality.beliefs import BeliefLedger, Evidence
from simreality.identity_evolution import IdentityChangeProposal
from simreality.identity_interpretation import (
    IdentityBeliefInterpreter, IdentityInterpretationRule, IdentityMemoryAssociation,
    IdentityRelationshipAssociation, IdentityPersonalityRule, NPCIdentityPersonality,
    NPCIdentityValues, IdentityValueRule,
)
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialInteraction, SocialTrustLedger
from simreality.model import NPC, NPCMemory, ActionTag, Description


class IdentityBeliefInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.proposal = IdentityChangeProposal(
            "event-1", "npc-a", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        self.interpreter = IdentityBeliefInterpreter((
            IdentityInterpretationRule("betrayal-policy", "claim-betrayal", 0.04),
        ))

    @staticmethod
    def belief(confidence):
        ledger = BeliefLedger({"claim-betrayal": 0.5})
        if confidence > 0.5:
            direction = 1
            strength = (confidence - 0.5) / 0.5
        else:
            direction = -1
            strength = (0.5 - confidence) / 0.5
        if strength:
            ledger.add(Evidence(
                "evidence-1", "claim-betrayal", "source", direction,
                strength, 1.0, 1,
            ))
        return ledger

    def test_same_event_is_interpreted_differently_by_individual_beliefs(self):
        other_proposal = IdentityChangeProposal(
            "event-1", "npc-b", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        results = self.interpreter.interpret(
            (self.proposal, other_proposal),
            {"npc-a": self.belief(0.9), "npc-b": self.belief(0.1)},
        )
        by_id = {item.interpreted.npc_id: item for item in results}
        self.assertAlmostEqual(by_id["npc-a"].interpreted.delta, 0.05)
        self.assertAlmostEqual(by_id["npc-b"].interpreted.delta, -0.012)
        self.assertAlmostEqual(by_id["npc-a"].belief_contributions[0][2], 0.032)
        self.assertAlmostEqual(by_id["npc-b"].belief_contributions[0][2], -0.032)

    def test_unknown_belief_is_neutral_and_policy_cap_is_preserved(self):
        result = self.interpreter.interpret((self.proposal,), {})[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertLessEqual(abs(result.interpreted.delta), 0.05)

    def test_social_beliefs_adapter_uses_each_observers_trust_sample(self):
        trust = SocialTrustLedger({("npc-a", "source"): 0.9, ("npc-b", "source"): 0.1})
        social = SocialBeliefSystem(trust)
        for npc_id in ("npc-a", "npc-b"):
            social.observe(npc_id, Evidence(
                "report-1", "claim-betrayal", "source", 1, 0.8, 0.5, 1,
            ))
        other_proposal = IdentityChangeProposal(
            "event-1", "npc-b", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        results = self.interpreter.interpret_from_social_beliefs(
            (self.proposal, other_proposal), social
        )
        by_id = {item.interpreted.npc_id: item for item in results}
        self.assertGreater(by_id["npc-a"].belief_contributions[0][1], 0.5)
        self.assertGreater(by_id["npc-a"].belief_contributions[0][1], by_id["npc-b"].belief_contributions[0][1])
        self.assertGreater(by_id["npc-a"].interpreted.delta, by_id["npc-b"].interpreted.delta)

    def test_social_beliefs_adapter_rejects_wrong_input(self):
        with self.assertRaises(TypeError):
            self.interpreter.interpret_from_social_beliefs((self.proposal,), {})

    def test_explicit_personal_memory_changes_interpretation_by_retention(self):
        npc_a = NPC("npc-a", memories=[NPCMemory(
            "npc-a", "person-x", 0.9, 0.9, 2.0, ActionTag.CRIME_ASSAULT, Description(),
        )])
        npc_b = NPC("npc-b", memories=[NPCMemory(
            "npc-b", "person-x", 0.2, 0.2, 2.0, ActionTag.CRIME_ASSAULT, Description(),
        )])
        proposal_a = IdentityChangeProposal(
            "event-memory", "npc-a", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        proposal_b = IdentityChangeProposal(
            "event-memory", "npc-b", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        associations = (
            IdentityMemoryAssociation("event-memory", "npc-a", "betrayal-policy", 0, 0.04),
            IdentityMemoryAssociation("event-memory", "npc-b", "betrayal-policy", 0, 0.04),
        )
        results = self.interpreter.interpret_with_memories(
            (proposal_a, proposal_b), {"npc-a": npc_a, "npc-b": npc_b}, associations,
        )
        by_id = {item.interpreted.npc_id: item for item in results}
        self.assertGreater(by_id["npc-a"].interpreted.delta, by_id["npc-b"].interpreted.delta)
        self.assertAlmostEqual(by_id["npc-a"].memory_contributions[0][2], 0.036)
        self.assertAlmostEqual(by_id["npc-b"].memory_contributions[0][2], 0.008)

    def test_relationship_trust_changes_identity_interpretation_per_observer(self):
        trust = SocialTrustLedger()
        trust.add_many((
            SocialInteraction("trust-a", "npc-a", "witness", 1, 0.8, 1),
            SocialInteraction("trust-b", "npc-b", "witness", -1, 0.8, 1),
        ))
        proposal_a = IdentityChangeProposal(
            "event-social", "npc-a", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        proposal_b = IdentityChangeProposal(
            "event-social", "npc-b", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        associations = (
            IdentityRelationshipAssociation("event-social", "npc-a", "betrayal-policy", "witness", 0.02),
            IdentityRelationshipAssociation("event-social", "npc-b", "betrayal-policy", "witness", 0.02),
        )
        results = self.interpreter.interpret_with_relationships(
            (proposal_a, proposal_b), trust, associations,
        )
        by_id = {item.interpreted.npc_id: item for item in results}
        self.assertAlmostEqual(by_id["npc-a"].relationship_contributions[0][1], 0.9)
        self.assertAlmostEqual(by_id["npc-b"].relationship_contributions[0][1], 0.1)
        self.assertGreater(by_id["npc-a"].interpreted.delta, by_id["npc-b"].interpreted.delta)
        self.assertAlmostEqual(by_id["npc-a"].relationship_contributions[0][2], 0.016)
        self.assertAlmostEqual(by_id["npc-b"].relationship_contributions[0][2], -0.016)

    def test_personality_axes_make_same_event_feel_different(self):
        proposal_b = IdentityChangeProposal(
            "event-personality", "npc-b", "betrayal-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.05,
        )
        profiles = {
            "npc-a": NPCIdentityPersonality("npc-a", {
                "fearfulness": 0.9, "openness": -0.2,
            }),
            "npc-b": NPCIdentityPersonality("npc-b", {
                "fearfulness": -0.5, "openness": 0.8,
            }),
        }
        rules = (
            IdentityPersonalityRule("betrayal-policy", "fearfulness", 0.02),
            IdentityPersonalityRule("betrayal-policy", "openness", 0.01),
        )
        results = self.interpreter.interpret_with_personality(
            (self.proposal, proposal_b), profiles, rules,
        )
        by_id = {item.interpreted.npc_id: item for item in results}
        self.assertGreater(by_id["npc-a"].interpreted.delta, by_id["npc-b"].interpreted.delta)
        self.assertAlmostEqual(by_id["npc-a"].personality_contributions[0][2], 0.018)
        self.assertAlmostEqual(by_id["npc-b"].personality_contributions[0][2], -0.01)
        self.assertLessEqual(abs(by_id["npc-a"].interpreted.delta), 0.05)

    def test_missing_personality_is_neutral_and_profile_is_immutable(self):
        profile = NPCIdentityPersonality("npc-a", {"stubbornness": 0.7})
        result = self.interpreter.interpret_with_personality(
            (self.proposal,), {"npc-a": profile},
            (IdentityPersonalityRule("betrayal-policy", "openness", 0.04),),
        )[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertAlmostEqual(result.personality_contributions[0][1], 0.0)
        with self.assertRaises(TypeError):
            profile.axes["stubbornness"] = -0.5
        with self.assertRaises(ValueError):
            NPCIdentityPersonality("npc-a", {"fearfulness": 1.1})
        with self.assertRaises(ValueError):
            IdentityPersonalityRule("betrayal-policy", "fearfulness", float("nan"))

    def test_personality_rules_reject_duplicates_and_mismatched_profiles(self):
        rule = IdentityPersonalityRule("betrayal-policy", "confidence", 0.02)
        with self.assertRaises(ValueError):
            self.interpreter.interpret_with_personality(
                (self.proposal,), {"npc-a": NPCIdentityPersonality("npc-b", {})},
                (rule,),
            )
        with self.assertRaises(ValueError):
            self.interpreter.interpret_with_personality(
                (self.proposal,), {},
                (rule, rule),
            )

    def test_unknown_relationship_is_neutral_and_associations_are_validated(self):
        association = IdentityRelationshipAssociation(
            "event-1", "npc-a", "betrayal-policy", "unknown", 0.04,
        )
        result = self.interpreter.interpret_with_relationships(
            (self.proposal,), SocialTrustLedger(), (association,),
        )[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertEqual(result.relationship_contributions[0][1], 0.5)
        with self.assertRaises(ValueError):
            IdentityRelationshipAssociation("event-1", "npc-a", "p", "npc-a", 0.1)
        with self.assertRaises(ValueError):
            IdentityRelationshipAssociation("event-1", "npc-a", "p", "other", 1.1)

    def test_memory_associations_must_be_explicit_and_valid(self):
        npc = NPC("npc-a", memories=[])
        neutral = self.interpreter.interpret_with_memories((self.proposal,), {"npc-a": npc}, ())
        self.assertEqual(neutral[0].memory_contributions, ())
        with self.assertRaises(ValueError):
            self.interpreter.interpret_with_memories(
                (self.proposal,), {"npc-a": npc},
                (IdentityMemoryAssociation("event-1", "npc-a", "betrayal-policy", 0, 0.1),),
            )
        with self.assertRaises(ValueError):
            IdentityMemoryAssociation("event-1", "npc-a", "betrayal-policy", 0, 1.1)

    def test_custom_policy_cap_survives_interpretation(self):
        proposal = IdentityChangeProposal(
            "event-cap", "npc-a", "wide-policy", "trust",
            0.2, 0.22, 0.02, 1.0, "participant", 0.08,
        )
        interpreter = IdentityBeliefInterpreter((
            IdentityInterpretationRule("wide-policy", "claim-betrayal", 0.08),
        ))
        result = interpreter.interpret(
            (proposal,), {"npc-a": self.belief(1.0)}
        )[0]
        self.assertEqual(result.interpreted.maximum_delta, 0.08)
        self.assertAlmostEqual(result.interpreted.delta, 0.08)

    def test_interpretation_does_not_decide_or_mutate_original_proposal(self):
        original = self.proposal
        result = self.interpreter.interpret(
            (original,), {"npc-a": self.belief(0.9)}
        )[0]
        self.assertIs(result.original, original)
        self.assertEqual(original.delta, 0.02)
        self.assertNotEqual(result.interpreted.delta, original.delta)

    def test_comprehensive_pipeline_combines_every_input_once_and_is_bounded(self):
        npc = NPC("npc-a", memories=[NPCMemory(
            "npc-a", "person-x", 0.8, 0.8, 1.0, ActionTag.CRIME_ASSAULT, Description(),
        )])
        trust = SocialTrustLedger()
        trust.add_many((SocialInteraction("trust-1", "npc-a", "ally", 1, 0.8, 1),))
        result = self.interpreter.interpret_comprehensively(
            (self.proposal,),
            beliefs_by_npc={"npc-a": self.belief(0.9)},
            npcs_by_id={"npc-a": npc},
            memory_associations=(
                IdentityMemoryAssociation("event-1", "npc-a", "betrayal-policy", 0, 0.01),
            ),
            trust=trust,
            relationship_associations=(
                IdentityRelationshipAssociation(
                    "event-1", "npc-a", "betrayal-policy", "ally", 0.01,
                ),
            ),
            personalities_by_npc={
                "npc-a": NPCIdentityPersonality("npc-a", {"caution": 0.5}),
            },
            personality_rules=(
                IdentityPersonalityRule("betrayal-policy", "caution", 0.01),
            ),
        )[0]
        self.assertAlmostEqual(result.belief_contributions[0][2], 0.032)
        self.assertAlmostEqual(result.memory_contributions[0][2], 0.008)
        self.assertAlmostEqual(result.relationship_contributions[0][2], 0.008)
        self.assertAlmostEqual(result.personality_contributions[0][2], 0.005)
        self.assertAlmostEqual(result.interpreted.delta, 0.05)
        self.assertIs(result.original, self.proposal)

    def test_value_priorities_contribute_to_comprehensive_appraisal(self):
        result = self.interpreter.interpret_comprehensively(
            (self.proposal,),
            values_by_npc={"npc-a": NPCIdentityValues("npc-a", {"loyalty": 0.8, "fairness": -0.4})},
            value_rules=(
                IdentityValueRule("betrayal-policy", "loyalty", 0.02),
                IdentityValueRule("betrayal-policy", "fairness", 0.01),
            ),
        )[0]
        contributions = {item[0]: item[2] for item in result.value_contributions}
        self.assertAlmostEqual(contributions["loyalty"], 0.016)
        self.assertAlmostEqual(contributions["fairness"], -0.004)
        self.assertAlmostEqual(result.interpreted.delta, 0.032)

    def test_missing_value_axis_is_neutral_and_profile_is_immutable(self):
        profile = NPCIdentityValues("npc-a", {"fairness": 0.5})
        result = self.interpreter.interpret_comprehensively(
            (self.proposal,), values_by_npc={"npc-a": profile},
            value_rules=(IdentityValueRule("betrayal-policy", "loyalty", 0.02),),
        )[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertEqual(result.value_contributions[0][1], 0.0)
        with self.assertRaises(TypeError):
            profile.axes["fairness"] = -0.5
        with self.assertRaises(ValueError):
            NPCIdentityValues("npc-a", {"loyalty": 1.1})

    def test_comprehensive_pipeline_missing_inputs_are_neutral(self):
        result = self.interpreter.interpret_comprehensively((self.proposal,))[0]
        self.assertAlmostEqual(result.interpreted.delta, self.proposal.delta)
        self.assertEqual(result.memory_contributions, ())
        self.assertEqual(result.relationship_contributions, ())
        self.assertEqual(result.personality_contributions, ())

    def test_comprehensive_pipeline_requires_trust_for_relationship_links(self):
        association = IdentityRelationshipAssociation(
            "event-1", "npc-a", "betrayal-policy", "ally", 0.01,
        )
        with self.assertRaises(ValueError):
            self.interpreter.interpret_comprehensively(
                (self.proposal,), relationship_associations=(association,),
            )

    def test_duplicate_rules_and_proposals_are_rejected(self):
        with self.assertRaises(ValueError):
            IdentityBeliefInterpreter((
                IdentityInterpretationRule("p", "c", 0.1),
                IdentityInterpretationRule("p", "c", 0.2),
            ))
        with self.assertRaises(ValueError):
            self.interpreter.interpret((self.proposal, self.proposal), {})


if __name__ == "__main__":
    unittest.main()
