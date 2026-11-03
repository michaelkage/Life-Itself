import unittest

from simreality.beliefs import BeliefLedger, Evidence
from simreality.identity_evolution import IdentityChangeProposal
from simreality.identity_interpretation import (
    IdentityBeliefInterpreter, IdentityInterpretationRule,
)
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_trust import SocialTrustLedger


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
        self.assertLess(by_id["npc-b"].belief_contributions[0][1], 0.5)
        self.assertGreater(by_id["npc-a"].interpreted.delta, by_id["npc-b"].interpreted.delta)

    def test_social_beliefs_adapter_rejects_wrong_input(self):
        with self.assertRaises(TypeError):
            self.interpreter.interpret_from_social_beliefs((self.proposal,), {})

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
