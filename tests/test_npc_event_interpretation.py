import unittest

from simreality import (
    EventInterpretationRule, NPCEventInterpreter, NPCInterpretationProfile,
    WorldEventLedger,
)


class NPCEventInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.event = WorldEventLedger.make_event(
            "meeting-1", 12, "workplace_meeting",
            participants=("npc-a", "manager"),
            witnesses=("npc-b",),
            attributes={"manager_tone": "raised", "outcome": "disciplinary"},
        )

    def test_observer_specific_rules_can_interpret_same_fact_differently(self):
        fearful = NPCInterpretationProfile("npc-a", (
            EventInterpretationRule("r1", "workplace_meeting", "raised_voice",
                                    -0.9, 0.8,
                                    required_attributes=(("manager_tone", "raised"),)),
        ))
        reassured = NPCInterpretationProfile("npc-b", (
            EventInterpretationRule("r2", "workplace_meeting", "manager_support",
                                    0.8, 0.6,
                                    required_attributes=(("outcome", "disciplinary"),)),
        ))
        a = NPCEventInterpreter.interpret(self.event, fearful)
        b = NPCEventInterpreter.interpret(self.event, reassured)
        self.assertEqual(a[0].outcome, -0.9)
        self.assertEqual(b[0].outcome, 0.8)
        self.assertNotEqual(a[0].cue, b[0].cue)

    def test_non_observer_does_not_receive_interpretation(self):
        profile = NPCInterpretationProfile("npc-c", (
            EventInterpretationRule("r", "workplace_meeting", "cue", -1),
        ))
        self.assertEqual(NPCEventInterpreter.interpret(self.event, profile), ())

    def test_attribute_constraints_prevent_false_rule_matches(self):
        profile = NPCInterpretationProfile("npc-a", (
            EventInterpretationRule(
                "r", "workplace_meeting", "cue", -1,
                required_attributes=(("manager_tone", "calm"),),
            ),
        ))
        self.assertEqual(NPCEventInterpreter.interpret(self.event, profile), ())

    def test_multiple_rules_produce_stable_proposals(self):
        rules = (
            EventInterpretationRule("z", "workplace_meeting", "z-cue", 0.2),
            EventInterpretationRule("a", "workplace_meeting", "a-cue", -0.2),
        )
        proposals = NPCEventInterpreter.interpret(
            self.event, NPCInterpretationProfile("npc-a", rules))
        self.assertEqual([item.rule_id for item in proposals], ["a", "z"])

    def test_invalid_profile_and_rule_rejected(self):
        with self.assertRaises(ValueError):
            EventInterpretationRule("r", "meeting", "cue", 2)
        with self.assertRaises(ValueError):
            NPCInterpretationProfile("npc", (
                EventInterpretationRule("same", "meeting", "a", 0),
                EventInterpretationRule("same", "meeting", "b", 0),
            ))


if __name__ == "__main__":
    unittest.main()
