"""Tests for deterministic memory-to-rumour preparation."""
import unittest

from simreality import ActionTag, AgeBand, Description, NPC, NPCMemory, Weather
from simreality.memory_rumours import MemoryRumourAdapter


class MemoryRumourAdapterTests(unittest.TestCase):
    def setUp(self):
        self.npc = NPC("witness", age_band=AgeBand.YOUNG_ADULT)
        self.npc.remember(NPCMemory(
            witness_id="witness",
            target_entity_id="suspect",
            initial_impact=1.0,
            retention=1.0,
            timestamp_hour=0.0,
            action_tag=ActionTag.CRIME_THEFT,
            description=Description(
                height_m=1.82,
                height_uncertainty_m=0.2,
                jacket_colour_weights={"black": 0.8},
            ),
        ))
        self.adapter = MemoryRumourAdapter()

    def test_prepares_rumour_from_npc_memory(self):
        result = self.adapter.prepare(self.npc, 1.0, Weather.CLEAR)
        self.assertEqual(result.witness_id, "witness")
        self.assertEqual(len(result.memories), 1)
        self.assertEqual(len(result.rumours), 1)
        self.assertEqual(result.rumours[0].target_entity_id, "suspect")
        self.assertLess(result.rumours[0].retention, 1.0)

    def test_is_read_only_and_same_time_replay_is_identical(self):
        before = list(self.npc.memories)
        first = self.adapter.prepare(self.npc, 8.0, Weather.CLEAR)
        second = self.adapter.prepare(self.npc, 8.0, Weather.CLEAR)
        self.assertEqual(first.memories, second.memories)
        self.assertEqual(first.rumours, second.rumours)
        self.assertEqual(self.npc.memories, before)

    def test_later_time_does_not_mutate_or_double_decay_source(self):
        early = self.adapter.prepare(self.npc, 2.0, Weather.CLEAR)
        late = self.adapter.prepare(self.npc, 8.0, Weather.CLEAR)
        replay = self.adapter.prepare(self.npc, 8.0, Weather.CLEAR)
        self.assertGreater(early.memories[0].retention, late.memories[0].retention)
        self.assertEqual(late.memories, replay.memories)
        self.assertEqual(self.npc.memories[0].retention, 1.0)

    def test_weak_memory_cannot_create_an_attributed_accusation(self):
        self.npc.memories[0] = self.npc.memories[0].decayed_to(0.4)
        result = self.adapter.prepare(self.npc, 0.0, Weather.CLEAR)
        self.assertEqual(len(result.rumours), 1)
        self.assertIsNone(result.rumours[0].target_entity_id)

    def test_no_memory_means_no_rumour(self):
        empty = NPC("bystander")
        result = self.adapter.prepare(empty, 10.0, Weather.CLEAR)
        self.assertEqual(result.memories, ())
        self.assertEqual(result.rumours, ())

    def test_invalid_time_rejected(self):
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.adapter.prepare(self.npc, value, Weather.CLEAR)


if __name__ == "__main__":
    unittest.main()
