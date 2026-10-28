import unittest

from simreality import (
    ActionTag, NPC, ConversationIntent, SocialBeliefSystem,
    ObservedClaim, SocialConsequenceRecorder, SocialConversationAdapter, SocialTrustLedger, SimulationTickCoordinator,
    SimulationWorldCheckpoint, WitnessedSocialEvent, WorldEventLedger, WorldEventMemoryAdapter,
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
        consequences = SocialConsequenceRecorder(trust, beliefs)
        consequences.record(WitnessedSocialEvent(\n            "event-social-1", "listener", "speaker", 3, -1, 0.4,\n            (ObservedClaim("claim-1", 1, 0.7),),\n        ))
        intent = ConversationIntent("chat-3", "listener", "speaker")
        coordinator.step(3, npcs, event_ids=("event-1",), conversations=(intent,))
        return coordinator, npcs, consequences

    def test_round_trip_restores_dependencies_and_idempotent_tick_replay(self):
        coordinator, npcs, consequences = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},\n            consequence_recorder=consequences,
        ).to_json()

        restored_checkpoint = SimulationWorldCheckpoint.from_json(payload)
        restored = restored_checkpoint.restore()
        self.assertEqual(restored.current_tick, 4)
        self.assertEqual(restored.metadata, (("seed", 42), ("world", "alpha")))
        self.assertEqual(restored.memory_adapter.ticks_per_hour, 2.0)\n        self.assertIsNotNone(restored.consequence_recorder)\n        before_consequence_trust = restored.trust.snapshot()\n        replayed_consequence = restored.consequence_recorder.record(WitnessedSocialEvent(\n            "event-social-1", "listener", "speaker", 3, -1, 0.4,\n            (ObservedClaim("claim-1", 1, 0.7),),\n        ))\n        self.assertEqual(replayed_consequence.event_id, "event-social-1")\n        self.assertEqual(restored.trust.snapshot(), before_consequence_trust)

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
                metadata=dict(restored.metadata),\n                consequence_recorder=restored.consequence_recorder,
            ).to_json(),
            payload,
        )

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json('{"schema_version":99}')

    def test_invalid_clock_or_metadata_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(-1, coordinator, npcs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, metadata={"not-finite": float("nan")},
            )


if __name__ == "__main__":
    unittest.main()
