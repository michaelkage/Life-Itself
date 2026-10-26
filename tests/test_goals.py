"""Regression tests for deterministic NPC goal selection and dependencies."""
import unittest

from simreality.goals import GoalBook, GoalStatus, NPCGoal


class GoalBookTests(unittest.TestCase):
    def test_higher_priority_actionable_goal_wins(self):
        book = GoalBook()
        book.add(NPCGoal("rent", "npc", "security", priority=8, confidence=0.9))
        book.add(NPCGoal("hobby", "npc", "creative", priority=3, confidence=1.0))
        self.assertEqual(book.choose("npc", 0).goal_id, "rent")

    def test_prerequisite_blocks_goal_until_completed(self):
        book = GoalBook()
        book.add(NPCGoal("save", "npc", "finance", priority=4))
        book.add(NPCGoal("move", "npc", "housing", priority=10, dependencies=("save",)))
        self.assertEqual(book.choose("npc", 0).goal_id, "save")
        book.update_progress("save", 1.0)
        self.assertEqual(book.choose("npc", 0).goal_id, "move")

    def test_deadline_increases_urgency_deterministically(self):
        book = GoalBook()
        book.add(NPCGoal("urgent", "npc", "work", priority=5, created_tick=0,
                         deadline_tick=10, confidence=1.0))
        early = book.evaluate("urgent", 0)
        late = book.evaluate("urgent", 9)
        self.assertLess(early.score, late.score)
        self.assertEqual(late, book.evaluate("urgent", 9))

    def test_equal_scores_use_goal_id_as_stable_tiebreak(self):
        book = GoalBook()
        book.add(NPCGoal("zeta", "npc", "work", priority=5))
        book.add(NPCGoal("alpha", "npc", "work", priority=5))
        self.assertEqual(book.choose("npc", 0).goal_id, "alpha")

    def test_failed_prerequisite_makes_dependent_unactionable(self):
        book = GoalBook()
        book.add(NPCGoal("qualification", "npc", "education", priority=5))
        book.add(NPCGoal("promotion", "npc", "career", priority=9,
                         dependencies=("qualification",)))
        book.set_status("qualification", GoalStatus.FAILED)
        result = book.evaluate("promotion", 3)
        self.assertFalse(result.actionable)
        self.assertIn("no longer", result.reason)

    def test_unknown_prerequisite_is_rejected_without_corrupting_book(self):
        book = GoalBook()
        book.add(NPCGoal("first", "npc", "work", priority=1))
        with self.assertRaisesRegex(ValueError, "unknown goal dependency"):
            book.add(NPCGoal("second", "npc", "work", priority=1,
                             dependencies=("missing",)))
        self.assertEqual(set(book.goals), {"first"})

    def test_invalid_values_and_duplicate_ids_are_rejected(self):
        book = GoalBook()
        with self.assertRaises(ValueError):
            book.add(NPCGoal("bad", "npc", "work", priority=-1))
        book.add(NPCGoal("valid", "npc", "work", priority=1))
        with self.assertRaises(ValueError):
            book.add(NPCGoal("valid", "npc", "work", priority=2))

    def test_snapshot_is_stable_and_sorted(self):
        book = GoalBook()
        book.add(NPCGoal("z", "npc", "work", priority=1, related_entities=("b", "a")))
        book.add(NPCGoal("a", "npc", "home", priority=2))
        first = book.snapshot()
        second = book.snapshot()
        self.assertEqual(first, second)
        self.assertEqual(first[0][0], "a")
        self.assertEqual(first[1][10], ("a", "b"))


if __name__ == "__main__":
    unittest.main()
