import json
import unittest

from simreality.emotional_events import EmotionalEventRule, NPCEmotionalEventLedger
from simreality.emotional_events_save_state import EmotionalEventSnapshot
from simreality.world_events import WorldEventLedger


class EmotionalEventSnapshotTests(unittest.TestCase):
    def test_canonical_roundtrip_preserves_emotion_and_replay_history(self):
        ledger = NPCEmotionalEventLedger()
        event = WorldEventLedger.make_event(
            "loss-1", 3, "bereavement", participants=("npc-a",)
        )
        ledger.advance(
            3, (event,),
            event_rules=(EmotionalEventRule(
                "grief-on-loss", "bereavement", "participant", "grief", 0.8
            ),),
        )
        snapshot = EmotionalEventSnapshot.capture(ledger)
        restored = EmotionalEventSnapshot.from_json(snapshot.to_json()).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        restored.advance(
            8, (event,),
            event_rules=(EmotionalEventRule(
                "grief-on-loss", "bereavement", "participant", "grief", 0.8
            ),),
        )
        self.assertEqual(restored.state_for("npc-a").intensities["grief"], 0.8)

    def test_rejects_noncanonical_and_corrupt_payloads(self):
        ledger = NPCEmotionalEventLedger()
        raw = {
            "schema_version": 1,
            "current_tick": 0,
            "ledger": ledger.snapshot(),
        }
        noncanonical = json.dumps(raw, indent=2)
        with self.assertRaisesRegex(ValueError, "canonical"):
            EmotionalEventSnapshot.from_json(noncanonical)
        raw["ledger"]["current_tick"] = -1
        payload = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        with self.assertRaises(ValueError):
            EmotionalEventSnapshot.from_json(payload)

    def test_snapshot_is_independent_of_mutable_source_ledger(self):
        ledger = NPCEmotionalEventLedger()
        snapshot = EmotionalEventSnapshot.capture(ledger)
        ledger.advance(4, (), event_rules=())
        restored = snapshot.restore()
        self.assertEqual(restored.current_tick, 0)


if __name__ == "__main__":
    unittest.main()
