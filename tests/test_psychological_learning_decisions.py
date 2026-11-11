import unittest

from simreality.psychological_conditioning import ConditioningProfile, NPCConditioningLedger
from simreality.psychological_interpretation import LearningProposal
from simreality.psychological_learning_decisions import (
    PsychologicalLearningDecisionLedger, PsychologicalLearningDecisionSnapshot,
)


class PsychologicalLearningDecisionTests(unittest.TestCase):
    def setUp(self):
        self.conditioning = NPCConditioningLedger()
        self.profile = ConditioningProfile("npc-a", learning_rate=0.5)
        self.positive = LearningProposal("npc-a", "event-1", 1, "rule-1",
                                         "authority", 1.0, 1.0, "reinforce", "authority is safe")

    def test_accept_applies_learning_once_and_replay_is_idempotent(self):
        ledger = PsychologicalLearningDecisionLedger()
        decision = ledger.decide("d1", self.positive, accepted=True,
                                 decision_tick=2, conditioning=self.conditioning,
                                 profile=self.profile, rationale="I trust them")
        self.assertEqual(self.conditioning.association_for("npc-a", "authority"), 0.5)
        self.assertEqual(len(self.conditioning.records()), 1)
        self.assertEqual(ledger.decide("d1", self.positive, accepted=True,
                                       decision_tick=2, conditioning=self.conditioning,
                                       profile=self.profile, rationale="I trust them"), decision)
        self.assertEqual(len(self.conditioning.records()), 1)

    def test_rejection_is_preserved_without_conditioning_change(self):
        ledger = PsychologicalLearningDecisionLedger()
        decision = ledger.decide("d1", self.positive, accepted=False,
                                 decision_tick=2, conditioning=self.conditioning,
                                 profile=self.profile, rationale="Not convinced")
        self.assertFalse(decision.accepted)
        self.assertEqual(self.conditioning.association_for("npc-a", "authority"), 0.0)
        self.assertEqual(self.conditioning.records(), ())
        self.assertEqual(ledger.entries(), (decision,))

    def test_conflicting_replay_and_second_decision_are_rejected(self):
        ledger = PsychologicalLearningDecisionLedger()
        ledger.decide("d1", self.positive, accepted=False, decision_tick=2,
                      conditioning=self.conditioning, profile=self.profile,
                      rationale="Reject this conflicting replay")
        with self.assertRaisesRegex(ValueError, "conflicting content"):
            ledger.decide("d1", self.positive, accepted=True, decision_tick=2,
                          conditioning=self.conditioning, profile=self.profile,
                          rationale="Conflicting acceptance")
        with self.assertRaisesRegex(ValueError, "already has a decision"):
            ledger.decide("d2", self.positive, accepted=True, decision_tick=2,
                          conditioning=self.conditioning, profile=self.profile,
                          rationale="Second decision for same proposal")

    def test_later_contradictory_learning_can_revise_association(self):
        ledger = PsychologicalLearningDecisionLedger()
        ledger.decide("d1", self.positive, accepted=True, decision_tick=2,
                      conditioning=self.conditioning, profile=self.profile,
                      rationale="Initial conditioning")
        negative = LearningProposal("npc-a", "event-2", 3, "rule-2",
                                    "authority", -1.0, 1.0, "reinforce", "authority is dangerous")
        ledger.decide("d2", negative, accepted=True, decision_tick=4,
                      conditioning=self.conditioning, profile=self.profile,
                      rationale="Update after contradictory evidence")
        self.assertEqual(self.conditioning.association_for("npc-a", "authority"), -0.25)

    def test_snapshot_round_trip_preserves_acceptance_and_rejection(self):
        ledger = PsychologicalLearningDecisionLedger()
        ledger.decide("d1", self.positive, accepted=True, decision_tick=2,
                      conditioning=self.conditioning, profile=self.profile)
        rejected = LearningProposal("npc-a", "event-2", 3, "rule-2",
                                    "crowds", -1.0, 0.5, "reinforce", "crowds are unsafe")
        ledger.decide("d2", rejected, accepted=False, decision_tick=4,
                      conditioning=self.conditioning, profile=self.profile, rationale="Second thought")
        encoded = PsychologicalLearningDecisionSnapshot.capture(ledger).to_json()
        restored = PsychologicalLearningDecisionSnapshot.from_json(encoded).restore()
        self.assertEqual(restored.entries(), ledger.entries())
        self.assertEqual(PsychologicalLearningDecisionSnapshot.capture(restored).to_json(), encoded)

    def test_snapshot_rejects_boolean_schema_version(self):
        encoded = PsychologicalLearningDecisionSnapshot.capture(
            PsychologicalLearningDecisionLedger()).to_json()
        malformed = encoded.replace('"schema_version":1', '"schema_version":true', 1)
        with self.assertRaisesRegex(ValueError, "schema"):
            PsychologicalLearningDecisionSnapshot.from_json(malformed)

    def test_failed_application_does_not_record_decision(self):
        ledger = PsychologicalLearningDecisionLedger()
        with self.assertRaisesRegex(ValueError, "profile owner"):
            ledger.decide("d1", self.positive, accepted=True, decision_tick=2,
                          conditioning=self.conditioning,
                          profile=ConditioningProfile("another-npc"),
                          rationale="Attempt with foreign profile")
        self.assertEqual(ledger.entries(), ())
        self.assertEqual(self.conditioning.records(), ())


if __name__ == "__main__":
    unittest.main()
