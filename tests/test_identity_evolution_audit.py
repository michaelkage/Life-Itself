import unittest

from simreality.emotional_scars import EmotionalScar, NPCEmotionalScarLedger
from simreality.identity_decisions import IdentityDecisionLedger
from simreality.identity_evolution import IdentityChangeProposal, NPCIdentityProfile
from simreality.identity_evolution_audit import IdentityEvolutionAuditTrail
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.scar_identity_proposals import (
    ScarIdentityProposalEvidence, ScarIdentityProposalLedger,
)
from simreality.world_events import WorldEventLedger


class IdentityEvolutionAuditTrailTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "experience-1", 2, "incident", participants=("npc-a",),
            ),
        ))
        self.history = NPCLifeHistory()
        self.history.record(AutobiographicalMemory(
            "memory-a", "npc-a", "experience-1", 2, (),
            "I was frightened in the crowded room", 0.8, -0.1,
        ))
        self.scars = NPCEmotionalScarLedger()
        self.scars.add_scar(EmotionalScar(
            "scar-a", "npc-a", "experience-1", "memory-a",
            3, "fear", "crowded-room", 0.8,
        ))
        self.identities = IdentityDecisionLedger((
            NPCIdentityProfile("npc-a", {"trust": 0.2}),
        ))
        proposal = IdentityChangeProposal(
            "experience-1", "npc-a", "fear-to-trust:scar-a", "trust",
            0.2, 0.16, -0.04, 0.8, "participant", 0.05,
        )
        self.evidence = ScarIdentityProposalEvidence(
            proposal, "scar-a", "fear-to-trust", "fear",
            "crowded-room", 4, 0.8 * (0.999 ** 1),
        )
        self.proposals = ScarIdentityProposalLedger((self.evidence,))

    def test_audit_links_experience_scar_proposal_and_accepted_change(self):
        self.identities.decide(
            "decision-a", self.evidence.proposal, accepted=True,
            decision_tick=5, rationale="I choose to be more guarded",
        )
        record, = IdentityEvolutionAuditTrail.build(
            self.events, self.history, self.scars, self.proposals, self.identities,
        )
        self.assertEqual(record.event_id, "experience-1")
        self.assertEqual(record.memory_id, "memory-a")
        self.assertEqual(record.scar_id, "scar-a")
        self.assertEqual(record.status, "accepted")
        self.assertAlmostEqual(record.resulting_trait, 0.16)

    def test_rejection_and_pending_proposal_remain_distinct(self):
        rejected = IdentityDecisionLedger((NPCIdentityProfile("npc-a", {"trust": 0.2}),))
        rejected.decide(
            "decision-rejected", self.evidence.proposal, accepted=False,
            decision_tick=5, rationale="This does not define me",
        )
        rejected_record, = IdentityEvolutionAuditTrail.build(
            self.events, self.history, self.scars, self.proposals, rejected,
        )
        self.assertEqual(rejected_record.status, "rejected")
        self.assertAlmostEqual(rejected_record.resulting_trait, 0.2)
        pending = IdentityDecisionLedger((NPCIdentityProfile("npc-a", {"trust": 0.2}),))
        pending_record, = IdentityEvolutionAuditTrail.build(
            self.events, self.history, self.scars, self.proposals, pending,
        )
        self.assertEqual(pending_record.status, "pending")
        self.assertIsNone(pending_record.resulting_trait)

    def test_audit_rejects_decision_that_does_not_match_original_proposal(self):
        changed = IdentityChangeProposal(
            "experience-1", "npc-a", "fear-to-trust:scar-a", "trust",
            0.2, 0.25, 0.05, 0.8, "participant", 0.05,
        )
        self.identities.decide(
            "decision-conflict", changed, accepted=True,
            decision_tick=5, rationale="Conflicting proposal",
        )
        with self.assertRaisesRegex(ValueError, "disagrees with its original proposal"):
            IdentityEvolutionAuditTrail.build(
                self.events, self.history, self.scars, self.proposals, self.identities,
            )


if __name__ == "__main__":
    unittest.main()
