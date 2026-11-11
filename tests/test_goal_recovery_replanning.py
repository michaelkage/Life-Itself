"""Recovery-to-replanning integration tests."""
import unittest

from simreality.action_execution import ActionExecutionLedger
from simreality.goal_recovery import (
    GoalRecoveryEvaluator, GoalRecoveryReplanningAdapter, GoalRecoveryRule,
)
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.npc_action_replanning import NPCActionReplanningCoordinator
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.npc_goal_emergence import GoalLifecycleLedger
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger


class GoalRecoveryReplanningTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("housing", "npc-1", "housing", 9.0))
        self.lifecycle = GoalLifecycleLedger()
        self.lifecycle.transition(
            self.goals, "housing", GoalStatus.ABANDONED, 1,
            "No affordable housing was available",
        )
        self.rule = GoalRecoveryRule(
            "housing-return", "housing", need_key="financial_pressure",
            maximum_need_level=0.3, required_facts=("shelter_office_open",),
        )
        self.needs = {"financial_pressure": 0.2}
        self.available = frozenset({"shelter_office_open"})
        self.proposal = GoalRecoveryEvaluator.assess(
            self.goals, "npc-1", 2, rules=(self.rule,),
            need_levels=self.needs, available_facts=self.available,
        )[0]
        self.planner = DeterministicPlanner((
            PlanningAction("resume-obsolete-search", frozenset({"old_route"}), frozenset({"old_search_done"})),
            PlanningAction("apply-for-housing", frozenset({"shelter_office_open"}), frozenset({"housing_secured"})),
            PlanningAction("rest", frozenset({"safe_place"}), frozenset({"rested"})),
        ))
        self.events = WorldEventLedger()
        self.executions = ActionExecutionLedger(self.planner, (), self.events, self.goals)
        self.cycle = NPCDecisionCycle(self.goals, self.planner)
        self.coordinator = NPCActionReplanningCoordinator(
            self.cycle, self.executions, self.events,
        )

    def run_recovery(self, *, active_execution_id=None):
        return GoalRecoveryReplanningAdapter.recover_and_replan(
            self.proposal, self.goals, self.lifecycle, self.coordinator,
            need_levels=self.needs, available_facts=self.available,
            world_facts={"shelter_office_open"}, resources={},
            goal_facts={"housing": {"housing_secured"}, "rest": {"rested"}},
            active_execution_id=active_execution_id,
        )

    def test_recovery_immediately_plans_and_starts_relevant_action(self):
        result = self.run_recovery()
        self.assertEqual(self.goals.goals["housing"].status, GoalStatus.ACTIVE)
        self.assertEqual(result.replanning.decision.goal_id, "housing")
        self.assertEqual(result.replanning.action_id, "apply-for-housing")
        self.assertEqual(result.replanning.status, "started")
        self.assertEqual(result.lifecycle_event.from_status, "abandoned")
        self.assertEqual(result.lifecycle_event.to_status, "active")

    def test_old_active_execution_is_cancelled_before_replacement_starts(self):
        old = self.executions.start(
            "old-search", "npc-1", 1, "resume-obsolete-search",
            {"old_route"}, {}, plan_actions=("resume-obsolete-search",),
        )
        result = self.run_recovery(active_execution_id=old.execution_id)
        self.assertEqual(self.executions.get("old-search").status, "cancelled")
        self.assertEqual(result.replanning.action_id, "apply-for-housing")
        self.assertEqual(len(self.executions.active()), 1)

    def test_retry_reuses_lifecycle_event_and_replanning_result(self):
        first = self.run_recovery()
        second = self.run_recovery()
        self.assertEqual(first.lifecycle_event, second.lifecycle_event)
        self.assertEqual(first.replanning, second.replanning)
        self.assertEqual(len(self.executions.active()), 1)
        self.assertEqual(len(self.lifecycle.snapshot()), 2)

    def test_retry_rejects_goal_mutation_after_reopening(self):
        self.run_recovery()
        self.goals.goals["housing"].priority += 1.0
        with self.assertRaisesRegex(ValueError, "goal state changed"):
            self.run_recovery()

    def test_recovery_replans_from_current_facts_not_obsolete_route(self):
        result = self.run_recovery()
        self.assertNotIn("resume-obsolete-search", result.replanning.decision.plan.actions)
        self.assertEqual(result.replanning.decision.plan.actions, ("apply-for-housing",))


if __name__ == "__main__":
    unittest.main()
