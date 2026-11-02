import unittest
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.goal_save_state import GoalBookSnapshot

class GoalBookSnapshotTests(unittest.TestCase):
    def make_book(self):
        book = GoalBook()
        book.add(NPCGoal("career", "npc-1", "career", 0.8, created_tick=2,
                         deadline_tick=20, progress=0.25, confidence=0.7,
                         related_entities=("college", "shop"),
                         metadata={"qualification": "mechanic"}))
        book.add(NPCGoal("family", "npc-1", "family", 0.9,
                         status=GoalStatus.ABANDONED))
        return book

    def test_round_trip_preserves_goal_fields_and_order(self):
        book = self.make_book()
        encoded = GoalBookSnapshot.capture(book).to_json()
        restored = GoalBookSnapshot.from_json(encoded).restore()
        self.assertEqual(restored.snapshot(), book.snapshot())
        self.assertEqual(GoalBookSnapshot.capture(restored).to_json(), encoded)

    def test_invalid_schema_rejected(self):
        with self.assertRaises(ValueError):
            GoalBookSnapshot.from_json('{"schema_version":99,"records":[]}')

    def test_duplicate_or_unsorted_goal_ids_rejected(self):
        book = self.make_book()
        records = GoalBookSnapshot.capture(book).records
        with self.assertRaises(ValueError):
            GoalBookSnapshot((records[1], records[0]))

if __name__ == "__main__":
    unittest.main()
