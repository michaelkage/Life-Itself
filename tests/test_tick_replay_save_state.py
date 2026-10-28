import unittest

from simreality import (
    ActionTag, NPC, NPCCollectionSnapshot, SocialBeliefSnapshot,
    SocialConversationAdapter, SocialConversationReplaySnapshot,
    SocialTrustLedger, SocialTrustSnapshot, SimulationTickReplaySnapshot,
    SimulationTickCoordinator, WorldEventLedger, WorldEventMemoryAdapter,
    WorldEventMemoryReplaySnapshot,
)
from simreality.social_beliefs import SocialBeliefSystem
from simreality.simulation_tick import ConversationIntent


class SimulationTickReplayPersistenceTests(unittest.TestCase):
    def make_events(self):
        return WorldEventLedger((
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

    def test_round_trip_restores_cached_tick_result_without_reapplying_work(self):
        events = self.make_events()
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        memory_adapter = WorldEventMemoryAdapter(events)
        conversation_adapter = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory_adapter, conversation_adapter)
        npcs = {"speaker": NPC("speaker"), "listener": NPC("listener")}
        intent = ConversationIntent("chat-3", "listener", "speaker")
        original_result = coordinator.step(
            3, npcs, event_ids=("event-1",), conversations=(intent,),
        )

        tick_payload = SimulationTickReplaySnapshot.capture(coordinator).to_json()
        npc_payload = NPCCollectionSnapshot.capture(list(npcs.values())).to_json()
        memory_payload = WorldEventMemoryReplaySnapshot.capture(memory_adapter).to_json()
        trust_payload = SocialTrustSnapshot.capture(trust).to_json()
        belief_payload = SocialBeliefSnapshot.capture(beliefs).to_json()
        conversation_payload = SocialConversationReplaySnapshot.capture(conversation_adapter).to_json()

        restored_events = events.from_snapshot(events.snapshot())
        restored_npcs = NPCCollectionSnapshot.from_json(npc_payload).restore()
        restored_memory = WorldEventMemoryAdapter(restored_events)
        WorldEventMemoryReplaySnapshot.from_json(memory_payload).restore(restored_memory, restored_npcs)
        restored_trust = SocialTrustSnapshot.from_json(trust_payload).restore()
        restored_beliefs = SocialBeliefSnapshot.from_json(belief_payload).restore(restored_trust)
        restored_conversations = SocialConversationAdapter(restored_trust, restored_beliefs)
        SocialConversationReplaySnapshot.from_json(conversation_payload).restore(restored_conversations)
        restored_coordinator = SimulationTickCoordinator(restored_events, restored_memory, restored_conversations)
        SimulationTickReplaySnapshot.from_json(tick_payload).restore(restored_coordinator)

        before_listener_memories = list(restored_npcs["listener"].memories)
        replay = restored_coordinator.step(
            3, restored_npcs, event_ids=("event-1",), conversations=(intent,),
        )
        self.assertEqual(replay, original_result)
        self.assertEqual(restored_npcs["listener"].memories, before_listener_memories)
        self.assertEqual(len(restored_npcs["speaker"].memories), 1)
        self.assertEqual(SimulationTickReplaySnapshot.capture(restored_coordinator).to_json(), tick_payload)

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationTickReplaySnapshot.from_json('{"schema_version":88,"entries":[]}')

    def test_restore_requires_empty_coordinator(self):
        events = self.make_events()
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        memory = WorldEventMemoryAdapter(events)
        conversations = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        coordinator._last_tick = 1
        with self.assertRaises(ValueError):
            SimulationTickReplaySnapshot(()).restore(coordinator)


if __name__ == "__main__":
    unittest.main()
