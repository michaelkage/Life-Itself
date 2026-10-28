import unittest

from simreality import (
    ActionTag, NPC, NPCCollectionSnapshot, SocialTrustLedger,
    WorldEventLedger, WorldEventMemoryAdapter,
)
from simreality.adapter_replay_state import WorldEventMemoryReplaySnapshot


class WorldEventMemoryReplayPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "event-1", 4, "incident", witnesses=("witness",),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "target",
                    "memory_impact": 0.8,
                    "height_m": 1.8,
                    "jacket_colour": "dark",
                },
            ),
        ))
        self.adapter = WorldEventMemoryAdapter(self.events, ticks_per_hour=2.0)
        self.npcs = {"witness": NPC("witness")}
        self.memory = self.adapter.materialize("event-1", "witness", self.npcs)

    def test_json_round_trip_restores_replay_index_without_duplicate_memory(self):
        payload = WorldEventMemoryReplaySnapshot.capture(self.adapter).to_json()
        restored_npcs = NPCCollectionSnapshot.capture(list(self.npcs.values())).restore()
        restored_adapter = WorldEventMemoryAdapter(self.events, ticks_per_hour=2.0)
        snapshot = WorldEventMemoryReplaySnapshot.from_json(payload)
        snapshot.restore(restored_adapter, restored_npcs)

        replay = restored_adapter.materialize("event-1", "witness", restored_npcs)
        self.assertEqual(replay, self.memory)
        self.assertEqual(len(restored_npcs["witness"].memories), 1)
        self.assertEqual(WorldEventMemoryReplaySnapshot.capture(restored_adapter).to_json(), payload)

    def test_restore_refuses_when_npc_memory_was_not_restored(self):
        snapshot = WorldEventMemoryReplaySnapshot.capture(self.adapter)
        restored_adapter = WorldEventMemoryAdapter(self.events, ticks_per_hour=2.0)
        with self.assertRaisesRegex(ValueError, "absent from restored NPC"):
            snapshot.restore(restored_adapter, {"witness": NPC("witness")})
        self.assertEqual(restored_adapter.snapshot(), ())

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            WorldEventMemoryReplaySnapshot.from_json('{"schema_version":99,"entries":[]}')

    def test_duplicate_replay_keys_rejected(self):
        from simreality.model import NPCMemory, Description
        from simreality import ActionTag
        memory = NPCMemory("witness", "target", 0.8, 0.8, 2.0, ActionTag.CRIME_THEFT, Description())
        with self.assertRaises(ValueError):
            WorldEventMemoryReplaySnapshot((
                ("event-1", "witness", memory),
                ("event-1", "witness", memory),
            ))


if __name__ == "__main__":
    unittest.main()
