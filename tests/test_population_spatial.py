import unittest

from simreality.population_spatial import (
    PopulationLOD,
    PopulationSpatialScheduler,
)
from simreality.presence import NPCPresence, PresenceLedger


class PopulationSpatialSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.presence = PresenceLedger((
            NPCPresence("npc-a", "at_location", "district-1", None, None, 0.0, 0),
            NPCPresence("npc-b", "at_location", "district-1", None, None, 0.0, 0),
            NPCPresence("npc-c", "at_location", "district-2", None, None, 0.0, 0),
            NPCPresence("npc-d", "travelling", "road-node-4", "journey-d", "edge-4", 0.5, 0),
        ))
        self.scheduler = PopulationSpatialScheduler(self.presence)

    def test_partitions_by_authoritative_symbolic_presence_and_assigns_lod(self):
        result = self.scheduler.schedule(
            1, ("npc-a", "npc-b", "npc-c", "npc-d"),
            {"npc-a": 0.9, "npc-b": 0.4, "npc-c": 0.8, "npc-d": 0.1},
            full_budget=1, standard_budget=1, background_budget=1,
        )
        self.assertEqual(result.selected_owner_ids, ("npc-a", "npc-c", "npc-b"))
        self.assertEqual(result.deferred_owner_ids, ("npc-d",))
        by_cell = {item.cell_id: item for item in result.slices}
        self.assertEqual(by_cell["district-1"].lod, PopulationLOD.FULL)
        self.assertEqual(by_cell["district-2"].lod, PopulationLOD.STANDARD)
        self.assertEqual(by_cell["road-node-4"].lod, PopulationLOD.BACKGROUND)

    def test_identical_schedule_replay_is_idempotent(self):
        args = (1, ("npc-a", "npc-b"), {"npc-a": 0.9, "npc-b": 0.1})
        first = self.scheduler.schedule(*args, full_budget=1, standard_budget=1, background_budget=0)
        second = self.scheduler.schedule(*args, full_budget=1, standard_budget=1, background_budget=0)
        self.assertIs(first, second)

    def test_conflicting_replay_is_rejected(self):
        self.scheduler.schedule(
            1, ("npc-a",), {"npc-a": 0.9},
            full_budget=1, standard_budget=0, background_budget=0,
        )
        with self.assertRaisesRegex(ValueError, "conflicting population schedule"):
            self.scheduler.schedule(
                1, ("npc-a",), {"npc-a": 0.2},
                full_budget=1, standard_budget=0, background_budget=0,
            )

    def test_missing_presence_is_not_silently_assigned(self):
        with self.assertRaisesRegex(KeyError, "missing authoritative presence"):
            self.scheduler.schedule(
                1, ("npc-missing",), {"npc-missing": 0.5},
                full_budget=1, standard_budget=0, background_budget=0,
            )

    def test_invalid_budget_and_importance_are_rejected(self):
        with self.assertRaises(ValueError):
            self.scheduler.schedule(
                1, ("npc-a",), {"npc-a": 0.5},
                full_budget=-1, standard_budget=0, background_budget=0,
            )
        with self.assertRaises(ValueError):
            self.scheduler.schedule(
                1, ("npc-a",), {"npc-a": 1.5},
                full_budget=1, standard_budget=0, background_budget=0,
            )


if __name__ == "__main__":
    unittest.main()
