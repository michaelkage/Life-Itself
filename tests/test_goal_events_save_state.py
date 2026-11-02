import unittest
from simreality.goal_events import GoalEventAdapter, GoalProgressPolicy
from simreality.goal_events_save_state import GoalEventReplaySnapshot
from simreality.goals import GoalBook, NPCGoal
from simreality.world_events import WorldEventLedger

class GoalEventReplaySnapshotTests(unittest.TestCase):
    def test_replay_index_round_trip_prevents_double_progress(self):
        goals = GoalBook()
        goals.add(NPCGoal("g", "npc", "career", 1.0))
        policies = (GoalProgressPolicy("p", "milestone", "career", 0.25),)
        adapter = GoalEventAdapter(goals, policies)
        event = WorldEventLedger.make_event("e1", 1, "milestone", participants=("npc",))
        adapter.apply((event,))
        payload = GoalEventReplaySnapshot.capture(adapter).to_json()

        restored_goals = GoalBook()
        restored_goals.add(NPCGoal("g", "npc", "career", 1.0, progress=0.25))
        restored = GoalEventAdapter(restored_goals, policies)
        GoalEventReplaySnapshot.from_json(payload).restore(restored)
        self.assertEqual(restored.apply((event,)), ())
        self.assertEqual(restored_goals.goals["g"].progress, 0.25)
        self.assertEqual(GoalEventReplaySnapshot.capture(restored).to_json(), payload)

    def test_invalid_schema_rejected(self):
        with self.assertRaises(ValueError):
            GoalEventReplaySnapshot.from_json('{"schema_version":8,"entries":[]}')

if __name__ == "__main__":
    unittest.main()
