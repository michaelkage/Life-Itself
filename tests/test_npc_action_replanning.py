"""Tests for explicit, replay-safe NPC action replanning."""
import unittest

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_action_replanning import NPCActionReplanningCoordinator
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger


class NPCActionReplanningTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("repair", "npc-1", "maintenance", 8.0))
        self.goals.add(NPCGoal("rest", "npc-1", "wellbeing", 2.0))
        self.planner = DeterministicPlanner((
            PlanningAction("buy-parts", frozenset({"at-market"}), frozenset({"has-parts"})),
            PlanningAction("repair-machine", frozenset({"has-parts"}), frozenset({"machine-fixed"})),
            PlanningAction("rest", frozenset({"safe-place"}), frozenset({"rested"})),
            PlanningAction("repair-with-kit", frozenset({"has-kit"}), frozenset({"machine-fixed"})),
        ))
        self.events = WorldEventLedger()
        self.ledger = ActionExecutionLedger(
            self.planner,
            (ActionExecutionPolicy("buy-parts", (("cash", 4.0),)),
             ActionExecutionPolicy("repair-machine")),
            self.events, self.goals,
        )
        self.cycle = NPCDecisionCycle(self.goals, self.planner)
        self.coordinator = NPCActionReplanningCoordinator(self.cycle, self.ledger)

    def test_changed_preconditions_replan_to_alternate_path(self):
        result = self.coordinator.replan(
            "npc-1", 1, {"has-kit"}, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="market access lost",
        )
        self.assertEqual(result.status, "started")
        self.assertEqual(result.action_id, "repair-with-kit")
        self.assertEqual(result.decision.plan.actions, ("repair-with-kit",))

    def test_priority_change_cancels_old_action_and_starts_new_goal(self):
        self.ledger.start(
            "old-work", "npc-1", 1, "buy-parts", {"at-market"}, {"cash": 10.0},
            plan_actions=("buy-parts", "repair-machine"),
        )
        self.goals.goals["rest"].priority = 20.0
        result = self.coordinator.replan(
            "npc-1", 2, {"safe-place"}, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="wellbeing priority increased", active_execution_id="old-work",
        )
        self.assertEqual(result.decision.goal_id, "rest")
        self.assertEqual(result.action_id, "rest")
        self.assertEqual(self.ledger.get("old-work").status, "cancelled")
        self.assertIsNotNone(self.events.get("action-execution:old-work:finished"))

    def test_resource_shortage_blocks_without_spending(self):
        facts, resources = {"at-market"}, {"cash": 2.0}
        result = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="cash unavailable",
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("only 2 is available", result.rejected_reason)
        self.assertEqual(resources, {"cash": 2.0})
        self.assertEqual(facts, {"at-market"})
        self.assertEqual(self.ledger.active(), ())

    def test_interruption_replanning_preserves_terminal_history(self):
        self.ledger.start(
            "interrupted-work", "npc-1", 1, "buy-parts", {"at-market"}, {"cash": 10.0},
            plan_actions=("buy-parts", "repair-machine"),
        )
        self.ledger.advance("interrupted-work", 2, {"at-market"}, {"cash": 10.0},
                            interruption="market closed")
        result = self.coordinator.replan(
            "npc-1", 3, {"has-kit"}, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="interrupted action",
        )
        self.assertEqual(result.action_id, "repair-with-kit")
        self.assertEqual(self.ledger.get("interrupted-work").status, "interrupted")
        self.assertIsNotNone(self.events.get("action-execution:interrupted-work:finished"))


    def test_completed_action_automatically_starts_next_plan_step(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        self.assertEqual(first.action_id, "buy-parts")
        progression = self.coordinator.advance(
            first.execution_id, 2, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(progression.execution.status, "completed")
        self.assertEqual(progression.next_active.action_id, "repair-machine")
        self.assertEqual(progression.next_active.action_index, 1)
        final = self.coordinator.advance(
            progression.next_active.execution_id, 3, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(final.execution.status, "completed")
        self.assertIsNone(final.next_active)
        self.assertIn("machine-fixed", facts)
        self.assertEqual(resources["cash"], 6.0)

    def test_interrupted_action_automatically_replans_from_live_state(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        progression = self.coordinator.advance(
            first.execution_id, 2, {"has-kit"}, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            interruption="market closed and kit found",
        )
        self.assertEqual(progression.execution.status, "interrupted")
        self.assertEqual(progression.replanning.action_id, "repair-with-kit")
        self.assertEqual(self.ledger.get(first.execution_id).status, "interrupted")

    def test_identical_replan_request_is_replay_safe(self):
        args = ("npc-1", 1, {"has-kit"}, {"cash": 10.0},
                {"repair": {"machine-fixed"}, "rest": {"rested"}})
        first = self.coordinator.replan(*args, reason="retry")
        second = self.coordinator.replan(*args, reason="retry")
        self.assertEqual(first, second)
        self.assertEqual(len(self.ledger.active()), 1)
        self.assertIsNotNone(self.events.get(first.event_id))

    def test_replanning_preserves_prior_execution_records(self):
        facts = {"has-kit"}
        self.ledger.execute("completed-before-replan", "npc-1", 1, "repair-with-kit",
                            facts, {}, plan_actions=("repair-with-kit",))
        result = self.coordinator.replan(
            "npc-1", 2, facts, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="verify history",
        )
        self.assertEqual(result.status, "already_satisfied")
        self.assertEqual(self.ledger.get("completed-before-replan").status, "completed")


if __name__ == "__main__":
    unittest.main()
