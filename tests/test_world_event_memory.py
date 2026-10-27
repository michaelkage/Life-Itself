"""Tests for converting shared events into witness-specific memories."""
import unittest

from simreality.model import ActionTag, NPC
from simreality.world_events import WorldEventLedger
from simreality.world_event_memory import WorldEventMemoryAdapter


class WorldEventMemoryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "theft-1", 8, "crime",
                participants=("shopkeeper", "suspect"),
                witnesses=("shopkeeper", "guard"),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "suspect",
                    "memory_impact": 0.8,
                    "height_m": 1.82,
                    "height_uncertainty_m": 0.2,
                    "jacket_colour": "dark",
                    "jacket_colour_confidence": 0.7,
                    "masked": True,
                    "masked_confidence": 0.9,
                },
            ),
        ))
        self.adapter = WorldEventMemoryAdapter(self.events, ticks_per_hour=2)
        self.npcs = {"shopkeeper": NPC("shopkeeper"), "guard": NPC("guard")}

    def test_creates_memory_with_event_time_and_details(self):
        memory = self.adapter.materialize("theft-1", "guard", self.npcs)
        self.assertEqual(memory.action_tag, ActionTag.CRIME_THEFT)
        self.assertEqual(memory.target_entity_id, "suspect")
        self.assertAlmostEqual(memory.timestamp_hour, 4.0)
        self.assertAlmostEqual(memory.retention, 0.8)
        self.assertTrue(memory.description.masked)
        self.assertEqual(memory.description.jacket_colour_weights, {"dark": 0.7})
        self.assertEqual(len(self.npcs["guard"].memories), 1)

    def test_replay_is_idempotent(self):
        first = self.adapter.materialize("theft-1", "guard", self.npcs)
        second = self.adapter.materialize("theft-1", "guard", self.npcs)
        self.assertEqual(first, second)
        self.assertEqual(len(self.npcs["guard"].memories), 1)

    def test_each_witness_gets_separate_memory(self):
        self.adapter.materialize("theft-1", "guard", self.npcs)
        self.adapter.materialize("theft-1", "shopkeeper", self.npcs)
        self.assertEqual(len(self.npcs["guard"].memories), 1)
        self.assertEqual(len(self.npcs["shopkeeper"].memories), 1)

    def test_non_witness_rejected(self):
        with self.assertRaises(ValueError):
            self.adapter.materialize("theft-1", "stranger", self.npcs)

    def test_unknown_action_tag_returns_no_memory(self):
        ledger = WorldEventLedger((
            WorldEventLedger.make_event(
                "unknown", 1, "incident", witnesses=("guard",),
                attributes={"action_tag": "Unknown", "target_entity_id": "suspect"},
            ),
        ))
        adapter = WorldEventMemoryAdapter(ledger)
        self.assertIsNone(adapter.materialize("unknown", "guard", self.npcs))
        self.assertEqual(len(self.npcs["guard"].memories), 0)

    def test_missing_required_memory_attributes_returns_none(self):
        ledger = WorldEventLedger((
            WorldEventLedger.make_event("unknown", 1, "incident", witnesses=("guard",)),
        ))
        adapter = WorldEventMemoryAdapter(ledger)
        self.assertIsNone(adapter.materialize("unknown", "guard", self.npcs))


if __name__ == "__main__":
    unittest.main()
