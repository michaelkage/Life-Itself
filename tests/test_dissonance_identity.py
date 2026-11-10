import unittest

from simreality.cognitive_dissonance import DissonanceInput
from simreality.dissonance_identity import DissonanceIdentityBridge, DissonanceIdentityRule
from simreality.identity_decisions import IdentityDecisionLedger
from simreality.identity_evolution import NPCIdentityProfile


class DissonanceIdentityBridgeTests(unittest.TestCase):
    def conflict(self, cid, tick, score=0.8, owner="npc-a"):
        return DissonanceInput(cid, owner, "belief_conflict", "Declared conflict",
                               "belief:a", "belief:b", score, 1.0, 1.0, tick)

    def test_repeated_conflicts_produce_small_identity_proposal(self):
        conflicts = (self.conflict("c1", 1), self.conflict("c2", 2))
        profile = NPCIdentityProfile("npc-a", {"trust": 0.2})
        rule = DissonanceIdentityRule("dissonance-trust", "belief_conflict",
                                      "trust", -0.1, minimum_conflicts=2,
                                      maximum_delta=0.02)
        results = DissonanceIdentityBridge.propose(
            conflicts, (profile,), (rule,),
            event_id_by_conflict={"c1": "event-1", "c2": "event-2"},
            role_by_npc={"npc-a": "witness"},
        )
        self.assertEqual(len(results), 1)
        assessment = results[0]
        self.assertEqual(assessment.conflict_ids, ("c1", "c2"))
        self.assertAlmostEqual(assessment.proposal.delta, -0.02)
        self.assertEqual(assessment.proposal.event_id, "event-2")
        self.assertEqual(profile.traits["trust"], 0.2)

    def test_below_repetition_threshold_produces_no_proposal(self):
        result = DissonanceIdentityBridge.propose(
            (self.conflict("c1", 1),), (NPCIdentityProfile("npc-a", {"trust": 0.2}),),
            (DissonanceIdentityRule("p", "belief_conflict", "trust", 0.1, 2),),
            event_id_by_conflict={"c1": "event-1"}, role_by_npc={"npc-a": "participant"})
        self.assertEqual(result, ())

    def test_proposal_requires_explicit_identity_acceptance(self):
        profile = NPCIdentityProfile("npc-a", {"trust": 0.2})
        results = DissonanceIdentityBridge.propose(
            (self.conflict("c1", 1), self.conflict("c2", 2)), (profile,),
            (DissonanceIdentityRule("p", "belief_conflict", "trust", 0.1, 2),),
            event_id_by_conflict={"c1": "event-1", "c2": "event-2"},
            role_by_npc={"npc-a": "participant"})
        proposal = results[0].proposal
        ledger = IdentityDecisionLedger((profile,))
        ledger.decide("identity-decision-1", proposal, accepted=False,
                      decision_tick=3, rationale="I refuse to change")
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.2)
        self.assertFalse(ledger.entries()[0].accepted)

    def test_invalid_role_or_missing_event_is_rejected(self):
        conflicts = (self.conflict("c1", 1), self.conflict("c2", 2))
        profile = NPCIdentityProfile("npc-a", {"trust": 0.2})
        rule = DissonanceIdentityRule("p", "belief_conflict", "trust", 0.1, 2)
        with self.assertRaisesRegex(ValueError, "event ID"):
            DissonanceIdentityBridge.propose(
                conflicts, (profile,), (rule,), event_id_by_conflict={},
                role_by_npc={"npc-a": "participant"})
        with self.assertRaisesRegex(ValueError, "role"):
            DissonanceIdentityBridge.propose(
                conflicts, (profile,), (rule,),
                event_id_by_conflict={"c1": "event-1", "c2": "event-2"},
                role_by_npc={"npc-a": "observer"})


if __name__ == "__main__":
    unittest.main()
