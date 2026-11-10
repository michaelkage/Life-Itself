import unittest

from simreality.beliefs import BeliefLedger, Evidence
from simreality.social_relationships import SocialRelationshipLedger
from simreality.world_events import WorldEventLedger
from simreality.relationship_interpretation import (
    NPCRelationshipInterpreter, RelationshipInterpretationProfile,
)


class NPCRelationshipInterpreterTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "court-event", 7, "testimony",
                participants=("defendant",), witnesses=("observer-a", "observer-b"),
            ),
        ))
        self.relationships = SocialRelationshipLedger()
        self.interpreter = NPCRelationshipInterpreter(self.events, self.relationships)

    def profile(self, observer, warmth, resentment):
        return RelationshipInterpretationProfile(
            observer,
            value_responses={
                "protective": {"warmth": warmth, "resentment": resentment},
            },
        )

    def test_same_evidence_can_create_opposite_interpretations(self):
        first = self.interpreter.interpret(
            "court-event", "observer-a", "defendant",
            self.profile("observer-a", 0.8, -0.2),
            value_impacts={"protective": 0.9},
        )
        second = self.interpreter.interpret(
            "court-event", "observer-b", "defendant",
            self.profile("observer-b", -0.7, 0.9),
            value_impacts={"protective": 0.9},
        )
        self.assertGreater(self.relationships.relationship("observer-a", "defendant").value("warmth"), 0)
        self.assertLess(self.relationships.relationship("observer-b", "defendant").value("warmth"), 0)
        self.assertGreater(self.relationships.relationship("observer-b", "defendant").value("resentment"), 0)
        self.assertNotEqual(first.changes, second.changes)

    def test_bias_cues_and_personal_beliefs_are_separate_inputs(self):
        beliefs = BeliefLedger()
        beliefs.observe("observer-a", Evidence(
            "evidence-1", "defendant-is-dangerous", "source", 1, 0.9, 0.8, 7,
        ))
        interpreter = NPCRelationshipInterpreter(self.events, self.relationships, beliefs)
        profile = RelationshipInterpretationProfile(
            "observer-a",
            value_responses={"justice": {"respect": 0.5}},
            bias_responses={"ingroup": {"warmth": 0.8}},
            claim_responses={"defendant-is-dangerous": {"fear": 0.7}},
        )
        result = interpreter.interpret(
            "court-event", "observer-a", "defendant", profile,
            value_impacts={"justice": 0.5}, bias_cues={"ingroup": 0.8},
        )
        self.assertAlmostEqual(self.relationships.relationship("observer-a", "defendant").value("respect"), 0.25)
        self.assertAlmostEqual(self.relationships.relationship("observer-a", "defendant").value("warmth"), 0.64)
        self.assertGreater(self.relationships.relationship("observer-a", "defendant").value("fear"), 0)
        self.assertTrue(any(source.startswith("belief:") for _, source, _ in result.contributions))

    def test_replay_is_idempotent_and_changed_interpretation_rejected(self):
        profile = self.profile("observer-a", 0.5, 0.2)
        args = ("court-event", "observer-a", "defendant", profile)
        first = self.interpreter.interpret(*args, value_impacts={"protective": 0.5})
        second = self.interpreter.interpret(*args, value_impacts={"protective": 0.5})
        self.assertEqual(first, second)
        self.assertEqual(len(self.relationships.snapshot()), len(first.changes))
        with self.assertRaisesRegex(ValueError, "different profile or evidence"):
            self.interpreter.interpret(*args, value_impacts={"protective": -0.5})

    def test_profile_must_belong_to_observer_and_witness_must_be_recorded(self):
        with self.assertRaisesRegex(ValueError, "different observer"):
            self.interpreter.interpret(
                "court-event", "observer-a", "defendant",
                self.profile("observer-b", 0.5, 0.2), value_impacts={"protective": 0.5},
            )
        with self.assertRaisesRegex(ValueError, "not recorded as a witness"):
            self.interpreter.interpret(
                "court-event", "stranger", "defendant",
                self.profile("stranger", 0.5, 0.2), value_impacts={"protective": 0.5},
            )

    def test_unknown_target_and_claim_without_belief_ledger_rejected(self):
        with self.assertRaisesRegex(ValueError, "not a participant"):
            self.interpreter.interpret(
                "court-event", "observer-a", "stranger",
                self.profile("observer-a", 0.5, 0.2), value_impacts={"protective": 0.5},
            )
        profile = RelationshipInterpretationProfile(
            "observer-a", {}, claim_responses={"some-claim": {"fear": 0.5}},
        )
        with self.assertRaisesRegex(ValueError, "require a BeliefLedger"):
            self.interpreter.interpret(
                "court-event", "observer-a", "defendant", profile, value_impacts={},
            )


if __name__ == "__main__":
    unittest.main()
