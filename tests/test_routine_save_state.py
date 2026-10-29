import unittest

from simreality.routines import RoutineBlock, RoutineBook
from simreality.routine_save_state import RoutineBookSnapshot


class RoutineBookSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.book = RoutineBook((
            RoutineBlock(
                "work", "npc-1", "work", "bakery", 480, 960,
                priority=0.9, flexibility_minutes=20,
                fallback_activity="call employer", fallback_location_id="home",
            ),
            RoutineBlock("lunch", "npc-2", "eat", "cafe", 720, 780),
        ))

    def test_round_trip_preserves_schedule_and_resolution(self):
        payload = RoutineBookSnapshot.capture(self.book).to_json()
        restored = RoutineBookSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), self.book.snapshot())
        block = restored.for_period("npc-1", 485)[0]
        self.assertEqual(block.activity, "work")
        self.assertEqual(
            RoutineBookSnapshot.capture(restored).to_json(),
            payload,
        )

    def test_unknown_schema_invalid_overlap_and_noncanonical_order_rejected(self):
        with self.assertRaises(ValueError):
            RoutineBookSnapshot.from_json('{"schema_version":8,"blocks":[]}')
        overlapping = RoutineBook((
            RoutineBlock("first", "npc-1", "work", "a", 480, 600),
        ))
        payload = RoutineBookSnapshot.capture(overlapping).to_json()
        import json
        raw = json.loads(payload)
        raw["blocks"].append(dict(raw["blocks"][0], routine_id="second", start_minute=550))
        with self.assertRaises(ValueError):
            RoutineBookSnapshot.from_json(json.dumps(raw))
        raw = json.loads(payload)
        raw["blocks"].append(dict(
            raw["blocks"][0], routine_id="aaa", owner_id="npc-2",
        ))
        with self.assertRaises(ValueError):
            RoutineBookSnapshot.from_json(json.dumps(raw))


if __name__ == "__main__":
    unittest.main()
