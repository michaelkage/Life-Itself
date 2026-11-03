import unittest

from simreality.emotional_events import (
    EmotionalDecayRule, EmotionalEventRule, NPCEmotionalEventLedger,
)
from simreality.world_events import WorldEventLedger


class NPCEmotionalEventLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = NPCEmotionalEventLedger()
        self.grief = EmotionalEventRule("bereaved-grief", "bereavement", "participant", "grief", 0.7)
        self.witness_fear = EmotionalEventRule("witness-fear", "bereavement", "witness", "fear", 0.3)
        self.decay = (EmotionalDecayRule("grief", 0.9), EmotionalDecayRule("fear", 0.8))

    def event(self, event_id="loss-1", tick=2, event_type="bereavement"):
        return WorldEventLedger.make_event(
            event_id, tick, event_type,
            participants=("npc-a",), witnesses=("npc-b",),
            attributes={"context": "close_relationship"},
        )

    def test_events_change_only_explicit_participants_and_witnesses(self):
        states = self.ledger.advance(2, (self.event(),),
                                     event_rules=(self.grief, self.witness_fear))
        by_id = {state.npc_id: dict(state.intensities) for state in states}
        self.assertEqual(by_id["npc-a"], {"grief": 0.7})
        self.assertEqual(by_id["npc-b"], {"fear": 0.3})

    def test_event_impulse_occurs_at_event_tick_then_decays_to_current_tick(self):
        state = self.ledger.advance(4, (self.event(),),
                                   event_rules=(self.grief,), decay_rules=self.decay)[0]
        self.assertEqual(state.npc_id, "npc-a")
        self.assertAlmostEqual(state.intensities["grief"], 0.7 * 0.9**2)
        self.assertEqual(state.sampled_tick, 4)

    def test_retries_and_snapshot_restore_are_idempotent(self):
        event = self.event()
        self.ledger.advance(2, (event,), event_rules=(self.grief,))
        restored = NPCEmotionalEventLedger.from_snapshot(self.ledger.snapshot())
        repeated = restored.advance(5, (event,), event_rules=(self.grief,),
                                    decay_rules=self.decay)
        self.assertAlmostEqual(repeated[0].intensities["grief"], 0.7 * 0.9**3)
        restored.advance(5, (event,), event_rules=(self.grief,), decay_rules=self.decay)
        self.assertAlmostEqual(restored.state_for("npc-a").intensities["grief"],
                               0.7 * 0.9**3)

    def test_conflicting_event_reuse_and_late_new_events_are_rejected(self):
        event = self.event()
        self.ledger.advance(3, (event,), event_rules=(self.grief,))
        conflict = self.event(event_id="loss-1", tick=2, event_type="betrayal")
        with self.assertRaisesRegex(ValueError, "conflicting content"):
            self.ledger.advance(3, (conflict,), event_rules=(self.grief,))
        with self.assertRaisesRegex(ValueError, "before current_tick"):
            self.ledger.advance(4, (self.event("late-arrival", tick=1),),
                                event_rules=(self.grief,))

    def test_decay_without_events_and_validation(self):
        self.ledger.advance(2, (self.event(),), event_rules=(self.grief,))
        state = self.ledger.advance(4, (), event_rules=(),
                                    decay_rules=(EmotionalDecayRule("grief", 0.5),))[0]
        self.assertAlmostEqual(state.intensities["grief"], 0.7 * 0.5**2)
        with self.assertRaises(ValueError):
            EmotionalEventRule("bad", "death", "observer", "grief", 0.2)
        with self.assertRaises(ValueError):
            EmotionalDecayRule("fear", 1.2)


if __name__ == "__main__":
    unittest.main()
