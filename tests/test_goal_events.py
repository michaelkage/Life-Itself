import unittest
from simreality.goal_events import GoalEventAdapter, GoalProgressPolicy
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.world_events import WorldEventLedger

class GoalEventAdapterTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("career", "npc-1", "career", 0.8))
        self.goals.add(NPCGoal("family", "npc-1", "family", 0.9))
        self.goals.add(NPCGoal("other", "npc-2", "career", 0.8))
        self.adapter = GoalEventAdapter(self.goals, (
            GoalProgressPolicy("training", "training_completed", "career", 0.25, (("qualification", "mechanic"),)),
        ))

    def event(self, event_id="e1", tick=1, qualification="mechanic"):
        return WorldEventLedger.make_event(event_id, tick, "training_completed",
            participants=("npc-1",), attributes={"qualification": qualification})

    def test_only_explicit_owner_category_and_attributes_match(self):
        updates = self.adapter.apply((self.event(),))
        self.assertEqual([u.goal_id for u in updates], ["career"])
        self.assertEqual(self.goals.goals["career"].progress, 0.25)
        self.assertEqual(self.goals.goals["family"].progress, 0.0)
        self.assertEqual(self.goals.goals["other"].progress, 0.0)

    def test_replay_is_idempotent(self):
        event = self.event()
        self.adapter.apply((event,))
        self.assertEqual(self.adapter.apply((event,)), ())
        self.assertEqual(self.goals.goals["career"].progress, 0.25)

    def test_nonmatching_attribute_does_not_advance(self):
        self.assertEqual(self.adapter.apply((self.event(qualification="cooking"),)), ())

    def test_progress_caps_and_completes(self):
        adapter = GoalEventAdapter(self.goals, (GoalProgressPolicy("step", "milestone", "career", 0.75),))
        events = (
            WorldEventLedger.make_event("m1", 1, "milestone", participants=("npc-1",)),
            WorldEventLedger.make_event("m2", 2, "milestone", participants=("npc-1",)),
        )
        adapter.apply(events)
        self.assertEqual(self.goals.goals["career"].progress, 1.0)
        self.assertEqual(self.goals.goals["career"].status, GoalStatus.COMPLETED)

    def test_conflicting_reuse_rejected_without_extra_progress(self):
        self.adapter.apply((self.event(),))
        with self.assertRaises(ValueError):
            self.adapter.apply((self.event(tick=2),))
        self.assertEqual(self.goals.goals["career"].progress, 0.25)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            GoalProgressPolicy("bad", "event", "career", 0.0)

if __name__ == "__main__":
    unittest.main()
