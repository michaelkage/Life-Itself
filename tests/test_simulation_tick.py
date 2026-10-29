"""Regression tests for deterministic tick orchestration."""
import unittest

from simreality.model import ActionTag, NPC
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger
from simreality.simulation_tick import ConversationIntent, SimulationTickCoordinator
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger


class TickCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "event-1", 3, "incident",
                participants=("speaker", "subject"),
                witnesses=("speaker",),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "subject",
                    "memory_impact": 0.9,
                },
            ),
        ))
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        conversations = SocialConversationAdapter(trust, beliefs)
        memory = WorldEventMemoryAdapter(self.events, ticks_per_hour=1)
        self.coordinator = SimulationTickCoordinator(self.events, memory, conversations)
        self.npcs = {"speaker": NPC("speaker"), "listener": NPC("listener")}

    def test_memories_precede_same_tick_conversation(self):
        result = self.coordinator.step(
            3, self.npcs, event_ids=("event-1",),
            conversations=(ConversationIntent("chat-3", "listener", "speaker"),),
        )
        self.assertEqual(len(self.npcs["speaker"].memories), 1)
        self.assertEqual(len(self.npcs["listener"].memories), 1)
        self.assertEqual(len(result.conversations), 1)

    def test_replay_is_idempotent(self):
        request = {
            "event_ids": ("event-1",),
            "conversations": (ConversationIntent("chat-3", "listener", "speaker"),),
        }
        first = self.coordinator.step(3, self.npcs, **request)
        second = self.coordinator.step(3, self.npcs, **request)
        self.assertIs(first, second)
        self.assertEqual(len(self.npcs["speaker"].memories), 1)
        self.assertEqual(len(self.npcs["listener"].memories), 1)

    def test_conflicting_replay_rejected(self):
        self.coordinator.step(3, self.npcs, event_ids=("event-1",))
        with self.assertRaises(ValueError):
            self.coordinator.step(3, self.npcs, event_ids=())

    def test_tick_must_increase(self):
        self.coordinator.step(3, self.npcs)
        with self.assertRaises(ValueError):
            self.coordinator.step(2, self.npcs)

    def test_event_tick_must_match(self):
        with self.assertRaises(ValueError):
            self.coordinator.step(4, self.npcs, event_ids=("event-1",))

    def test_missing_witness_fails_before_mutation(self):
        with self.assertRaises(KeyError):
            self.coordinator.step(3, {"listener": self.npcs["listener"]}, event_ids=("event-1",))
        self.assertEqual(self.npcs["speaker"].memories, [])

    def test_routine_phase_is_tick_scoped_and_checkpointable(self):
        self.coordinator.step(3, self.npcs)
        block = RoutineBlock("shift-1", "speaker", "work", "shop", 480, 960)
        book = RoutineBook((block,))
        ledger = RoutineExecutionLedger()
        traffic = RoutineDisruption(
            "traffic-1", "speaker", DisruptionKind.TRAFFIC,
            1.0, 480, 600, delay_minutes=20,
        )
        first = self.coordinator.execute_routines(
            3, 500, book, ledger,
            disruptions=(traffic,), outcome_samples={"shift-1": 0.2},
        )
        replay = self.coordinator.execute_routines(
            3, 500, book, ledger,
            disruptions=(traffic,), outcome_samples={"shift-1": 0.2},
        )
        self.assertEqual(first, replay)
        self.assertEqual(first[0].execution_id, "3:shift-1")
        self.assertEqual(first[0].resolution.routine_id, "shift-1")

    def test_routine_phase_rejects_a_stale_tick(self):
        self.coordinator.step(3, self.npcs)
        self.coordinator.step(4, self.npcs)
        book = RoutineBook((RoutineBlock("shift-1", "speaker", "work", "shop", 480, 960),))
        with self.assertRaisesRegex(ValueError, "latest completed world tick"):
            self.coordinator.execute_routines(
                3, 500, book, RoutineExecutionLedger(),
                outcome_samples={"shift-1": 0.2},
            )

    def test_routine_phase_requires_world_tick_and_explicit_samples(self):
        book = RoutineBook((RoutineBlock("shift-1", "speaker", "work", "shop", 480, 960),))
        ledger = RoutineExecutionLedger()
        with self.assertRaisesRegex(ValueError, "completed world tick"):
            self.coordinator.execute_routines(
                3, 500, book, ledger, outcome_samples={"shift-1": 0.2},
            )
        self.coordinator.step(3, self.npcs)
        with self.assertRaisesRegex(ValueError, "missing outcome sample"):
            self.coordinator.execute_routines(3, 500, book, ledger, outcome_samples={})

    def test_missing_conversation_participant_rejected(self):
        with self.assertRaises(KeyError):
            self.coordinator.step(
                3, self.npcs,
                conversations=(ConversationIntent("chat", "missing", "speaker"),),
            )


if __name__ == "__main__":
    unittest.main()
