import unittest

from simreality import (
    NPCConditioningLedger, PsychologicalTrigger, PsychologicalTriggerAdapter,
)


class PsychologicalTriggerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = NPCConditioningLedger(
            associations={
                ("npc-a", "raised_voice"): -0.8,
                ("npc-a", "uniform"): 0.6,
                ("npc-b", "raised_voice"): 0.9,
            }
        )

    def test_exact_cue_and_required_context_activate(self):
        trigger = PsychologicalTrigger(
            "trigger-1", "npc-a", "raised_voice",
            aliases=("shouting",), required_context=("workplace",),
        )
        result = PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("shouting",), ("workplace", "day"),
            (trigger,),
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].matched_cue, "shouting")
        self.assertEqual(result[0].response.direction, "avoid")

    def test_similar_cue_without_required_context_does_not_activate(self):
        trigger = PsychologicalTrigger(
            "trigger-1", "npc-a", "raised_voice",
            required_context=("workplace",),
        )
        result = PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("raised_voice",), ("home",), (trigger,),
        )
        self.assertEqual(result, ())

    def test_excluded_context_blocks_activation(self):
        trigger = PsychologicalTrigger(
            "trigger-1", "npc-a", "raised_voice",
            excluded_context=("trusted_friend",),
        )
        result = PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("raised_voice",),
            ("trusted_friend",), (trigger,),
        )
        self.assertEqual(result, ())

    def test_associations_are_individual(self):
        trigger_a = PsychologicalTrigger("a", "npc-a", "raised_voice")
        trigger_b = PsychologicalTrigger("b", "npc-b", "raised_voice")
        a = PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("raised_voice",), (), (trigger_a,))[0]
        b = PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-b", ("raised_voice",), (), (trigger_b,))[0]
        self.assertEqual(a.response.direction, "avoid")
        self.assertEqual(b.response.direction, "approach")

    def test_unknown_owner_triggers_are_ignored(self):
        trigger = PsychologicalTrigger("b", "npc-b", "raised_voice")
        self.assertEqual(PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("raised_voice",), (), (trigger,)), ())

    def test_invalid_context_and_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            PsychologicalTrigger("x", "npc-a", "cue",
                                 required_context=("indoors",),
                                 excluded_context=("indoors",))
        trigger = PsychologicalTrigger("same", "npc-a", "raised_voice")
        with self.assertRaises(ValueError):
            PsychologicalTriggerAdapter.evaluate(
                self.ledger, "npc-a", ("raised_voice",), (),
                (trigger, trigger),
            )

    def test_evaluation_is_read_only(self):
        before = self.ledger.snapshot()
        PsychologicalTriggerAdapter.evaluate(
            self.ledger, "npc-a", ("raised_voice",), (),
            (PsychologicalTrigger("t", "npc-a", "raised_voice"),),
        )
        self.assertEqual(before, self.ledger.snapshot())


if __name__ == "__main__":
    unittest.main()
