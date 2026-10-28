import unittest

from simreality import (
    ActionTag, NPC, ConversationIntent, SocialBeliefSystem,
    SocialConversationAdapter, SocialTrustLedger, SimulationTickCoordinator,
    SimulationWorldCheckpoint, WorldEventLedger, WorldEventMemoryAdapter,
)


class SimulationWorldCheckpointTests(unittest.TestCase):
    def make_simulation(self):
        events = WorldEventLedger((
            WorldEventLedger.make_event(
                "event-1", 3, "incident",
                participants=("speaker", "subject"), witnesses=("speaker",),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "subject",
                    "memory_impact": 0.9,
                },
            ),
        ))
        npcs = {"speaker": NPC("speaker"), "listener": NPC("listener")}
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        memory = WorldEventMemoryAdapter(events, ticks_per_hour=2.0)
        conversations = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        intent = ConversationIntent("chat-3", "listener", "speaker")
        coordinator.step(3, npcs, event_ids=("event-1",), conversations=(intent,))
        return coordinator, npcs

    def test_round_trip_restores_dependencies_and_idempotent_tick_replay(self):
        coordinator, npcs = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},
        ).to_json()

        restored_checkpoint = SimulationWorldCheckpoint.from_json(payload)
        restored = restored_checkpoint.restore()
        self.assertEqual(restored.current_tick, 4)
        self.assertEqual(restored.metadata, (("seed", 42), ("world", "alpha")))
        self.assertEqual(restored.memory_adapter.ticks_per_hour, 2.0)

        before = list(restored.npcs["speaker"].memories)
        result = restored.coordinator.step(
            3, restored.npcs, event_ids=("event-1",),
            conversations=(ConversationIntent("chat-3", "listener", "speaker"),),
        )
        self.assertEqual(restored.npcs["speaker"].memories, before)
        self.assertEqual(len(restored.npcs["speaker"].memories), 1)
        self.assertEqual(result.tick, 3)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                metadata=dict(restored.metadata),
            ).to_json(),
            payload,
        )

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json('{"schema_version":99}')

    def test_invalid_clock_or_metadata_rejected(self):
        coordinator, npcs = self.make_simulation()
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(-1, coordinator, npcs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, metadata={"not-finite": float("nan")},
            )


if __name__ == "__main__":
    unittest.main()
