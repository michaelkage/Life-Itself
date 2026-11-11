"""Tests for explicit, replay-safe NPC action replanning."""
import unittest
import hashlib
import json

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.action_evaluation import ActionPlanEvaluationLedger, NPCPlanEvaluation
from simreality.npc_strategy_beliefs import NPCStrategyBeliefLedger, StrategyLearningRule
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.goal_arbitration import (
    GoalArbitrationEvaluator, GoalCommitmentAdapter, GoalCommitmentLedger,
)
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



    def test_explicit_commitment_is_honored_by_action_replanning(self):
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 1, resources={"cash": 10.0}
        )
        commitments = GoalCommitmentLedger()
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, commitments, rationale="finish urgent repair"
        )
        result = self.coordinator.replan(
            "npc-1", 1, {"safe-place"}, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="honor current commitment", goal_commitment=commitment,
        )
        self.assertEqual(result.decision.goal_id, "repair")
        self.assertFalse(result.decision.actionable)
        self.assertEqual(result.status, "unplanned")
        self.assertEqual(self.ledger.active(), ())

    def test_replan_rejects_commitment_from_another_tick_or_owner(self):
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 1, resources={"cash": 10.0}
        )
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, GoalCommitmentLedger(), rationale="focus"
        )
        with self.assertRaisesRegex(ValueError, "owner and tick"):
            self.coordinator.replan(
                "npc-1", 2, {"safe-place"}, {"cash": 10.0},
                {"repair": {"machine-fixed"}, "rest": {"rested"}},
                reason="stale commitment", goal_commitment=commitment,
            )



    def test_stale_commitment_is_rejected_before_active_execution_is_cancelled(self):
        self.ledger.start(
            "preserve-current-work", "npc-1", 1, "buy-parts",
            {"at-market"}, {"cash": 10.0},
            plan_actions=("buy-parts", "repair-machine"),
        )
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 2, resources={"cash": 10.0}
        )
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, GoalCommitmentLedger(), rationale="repair"
        )
        self.goals.goals["repair"].status = GoalStatus.ABANDONED
        with self.assertRaisesRegex(ValueError, "commitment is stale"):
            self.coordinator.replan(
                "npc-1", 2, {"at-market"}, {"cash": 10.0},
                {"repair": {"machine-fixed"}, "rest": {"rested"}},
                reason="stale focus", active_execution_id="preserve-current-work",
                goal_commitment=commitment,
            )
        self.assertIsNotNone(self.ledger.active("preserve-current-work"))

    def test_commitment_aware_replan_snapshot_preserves_selected_goal(self):
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 1, resources={"cash": 10.0}
        )
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, GoalCommitmentLedger(), rationale="focus repair"
        )
        args = (
            "npc-1", 1, {"safe-place"}, {"cash": 10.0},
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        first = self.coordinator.replan(
            *args, reason="committed plan", goal_commitment=commitment,
        )
        snapshot = self.coordinator.to_snapshot()
        restored = NPCActionReplanningCoordinator.from_snapshot(
            self.cycle, self.ledger, self.events, snapshot,
        )
        replay = restored.replan(
            *args, reason="committed plan", goal_commitment=commitment,
        )
        self.assertEqual(replay, first)
        self.assertEqual(replay.decision.goal_id, commitment.selected_goal_id)
        self.assertEqual(restored.to_snapshot(), snapshot)

    def test_replanning_uses_explicit_owner_strategy_belief(self):
        goals = GoalBook()
        goals.add(NPCGoal("repair", "npc-1", "maintenance", 8.0))
        planner = DeterministicPlanner((
            PlanningAction("a-learned-unreliable", frozenset({"start"}), frozenset({"fixed"})),
            PlanningAction("z-alternative", frozenset({"start"}), frozenset({"fixed"})),
        ))
        events = WorldEventLedger()
        executions = ActionExecutionLedger(planner, (), events)
        cycle = NPCDecisionCycle(goals, planner)
        coordinator = NPCActionReplanningCoordinator(cycle, executions)
        beliefs = NPCStrategyBeliefLedger()
        observations = []
        for index in range(3):
            evaluation = NPCPlanEvaluation(
                f"failed-plan-{index}", "npc-1", "repair",
                ("a-learned-unreliable",), "failed", ("fixed",), (),
                ("fixed",), (), ("a-learned-unreliable",), (),
                (), 1.0,
            )
            observations.append(beliefs.observe_evaluation(
                evaluation, "workshop", observed_tick=index + 1,
            ))
        proposal = beliefs.assess(
            "npc-1", observations[0].strategy_id, "workshop",
            StrategyLearningRule("route-reliability", minimum_observations=3),
        )
        beliefs.decide(proposal, accepted=True, decision_tick=4,
                       rationale="This route repeatedly failed")
        result = coordinator.replan(
            "npc-1", 5, {"start"}, {},
            {"repair": {"fixed"}}, reason="apply accepted strategy learning",
            strategy_beliefs=beliefs, strategy_context_key="workshop",
        )
        self.assertEqual(result.decision.plan.actions, ("z-alternative",))
        event = events.get(result.event_id)
        self.assertIn("strategy_belief_sources", dict(event.attributes))
        self.assertEqual(len(json.loads(dict(event.attributes)["strategy_belief_sources"])), 1)

    def test_replanning_prefers_actions_with_better_observed_reliability(self):
        goals = GoalBook()
        goals.add(NPCGoal("goal", "npc-1", "maintenance", 8.0))
        planner = DeterministicPlanner((
            PlanningAction("a-unreliable", frozenset({"start"}), frozenset({"done"})),
            PlanningAction("z-reliable", frozenset({"start"}), frozenset({"done"})),
        ))
        events = WorldEventLedger()
        executions = ActionExecutionLedger(planner, (), events)
        evaluations = ActionPlanEvaluationLedger(
            executions, learning_min_samples=1, learning_rate=1.0,
        )
        executions.start(
            "bad-sample", "npc-1", 1, "a-unreliable", {"start"}, {},
            plan_actions=("a-unreliable",),
        )
        executions.cancel("bad-sample", 2, "failed attempt")
        evaluations.evaluate("bad-sample")
        executions.execute(
            "good-sample", "npc-1", 3, "z-reliable", {"start"}, {},
            plan_actions=("z-reliable",),
        )
        evaluations.evaluate("good-sample")
        self.assertEqual(evaluations.reliability("a-unreliable"), 0.0)
        self.assertEqual(evaluations.reliability("z-reliable"), 1.0)
        coordinator = NPCActionReplanningCoordinator(
            NPCDecisionCycle(goals, planner), executions, events, evaluations,
        )
        result = coordinator.replan(
            "npc-1", 4, {"start"}, {},
            {"goal": {"done"}}, reason="choose reliable route",
        )
        self.assertEqual(result.action_id, "z-reliable")

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


    def test_replanning_snapshot_restores_idempotency_cache(self):
        args = ("npc-1", 1, {"has-kit"}, {"cash": 10.0},
                {"repair": {"machine-fixed"}, "rest": {"rested"}})
        first = self.coordinator.replan(*args, reason="persist cache")
        snapshot = self.coordinator.to_snapshot()
        restored = NPCActionReplanningCoordinator.from_snapshot(
            self.cycle, self.ledger, self.events, snapshot,
        )
        second = restored.replan(*args, reason="persist cache")
        self.assertEqual(first, second)
        self.assertEqual(len(self.ledger.active()), 1)
        self.assertEqual(restored.to_snapshot(), snapshot)

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


    def test_interrupted_plan_resumes_at_original_action_and_continues_suffix(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        self.assertEqual(first.decision.plan.actions, ("buy-parts", "repair-machine"))
        interrupted = self.ledger.advance(
            first.execution_id, 2, facts, resources,
            interruption="temporary market closure",
        )
        self.assertEqual(interrupted.status, "interrupted")

        resumed = self.coordinator.resume_interrupted(
            first.execution_id, 3, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(resumed.original_action_index, 0)
        self.assertEqual(resumed.continuation_plan, ("buy-parts", "repair-machine"))
        self.assertEqual(resumed.execution.action_id, "buy-parts")
        self.assertEqual(resumed.execution.plan_actions, ("buy-parts", "repair-machine"))
        self.assertEqual(self.ledger.get(first.execution_id).status, "interrupted")

        progression = self.coordinator.advance(
            resumed.execution.execution_id, 4, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(progression.execution.status, "completed")
        self.assertEqual(progression.next_active.action_id, "repair-machine")
        self.assertEqual(progression.next_active.action_index, 1)

    def test_interrupted_later_plan_step_resumes_without_repeating_completed_work(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        first_step = self.coordinator.advance(
            first.execution_id, 2, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(first_step.execution.status, "completed")
        second_id = first_step.next_active.execution_id
        interrupted = self.ledger.advance(
            second_id, 3, facts, resources, interruption="repair tool jammed",
        )
        self.assertEqual(interrupted.status, "interrupted")

        resumed = self.coordinator.resume_interrupted(
            second_id, 4, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(resumed.original_action_index, 1)
        self.assertEqual(resumed.continuation_plan, ("repair-machine",))
        self.assertEqual(resumed.execution.action_id, "repair-machine")
        self.assertEqual(resumed.execution.action_index, 0)
        self.assertEqual(self.ledger.get(first.execution_id).status, "completed")

    def test_resume_is_idempotent_and_rechecks_live_preconditions(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        self.ledger.advance(
            first.execution_id, 2, facts, resources,
            interruption="temporary interruption",
        )
        with self.assertRaisesRegex(ValueError, "preconditions"):
            self.coordinator.resume_interrupted(
                first.execution_id, 3, {"safe-place"}, resources,
                {"repair": {"machine-fixed"}, "rest": {"rested"}},
            )
        resumed = self.coordinator.resume_interrupted(
            first.execution_id, 3, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        replay = self.coordinator.resume_interrupted(
            first.execution_id, 3, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(replay, resumed)
        self.assertEqual(len(self.ledger.active()), 1)
        resume_identity = hashlib.sha256(
            f"{first.execution_id}:3".encode("utf-8")
        ).hexdigest()[:24]
        resume_event = self.events.get(f"npc-action-resume:{resume_identity}")
        self.assertEqual(resume_event.event_type, "npc_action_resumed")
        self.assertEqual(dict(resume_event.attributes)["original_execution_id"],
                         first.execution_id)

    def test_interruption_is_replanned_not_counted_as_goal_execution_failure(self):
        evaluations = ActionPlanEvaluationLedger(self.ledger, self.events)
        coordinator = NPCActionReplanningCoordinator(
            self.cycle, self.ledger, self.events, evaluations,
        )
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        progression = coordinator.advance(
            first.execution_id, 2, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            interruption="temporary interruption",
        )
        self.assertEqual(progression.execution.status, "interrupted")
        self.assertEqual(progression.plan_evaluation.terminal_status, "replanned")

    def test_interrupted_plan_cursor_survives_execution_and_replanning_restore(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        self.ledger.advance(
            first.execution_id, 2, facts, resources,
            interruption="temporary interruption before checkpoint",
        )
        execution_snapshot = self.ledger.to_snapshot()
        replanning_snapshot = self.coordinator.to_snapshot()
        restored_ledger = ActionExecutionLedger.from_snapshot(
            self.planner, tuple(self.ledger.policies.values()),
            self.events, execution_snapshot, self.goals,
        )
        restored_coordinator = NPCActionReplanningCoordinator.from_snapshot(
            self.cycle, restored_ledger, self.events, replanning_snapshot,
        )
        resumed = restored_coordinator.resume_interrupted(
            first.execution_id, 3, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
        )
        self.assertEqual(resumed.continuation_plan,
                         ("buy-parts", "repair-machine"))
        self.assertEqual(resumed.execution.action_id, "buy-parts")
        self.assertEqual(restored_ledger.get(first.execution_id).status,
                         "interrupted")

    def test_resume_rejects_resource_shortage_and_parallel_owner_work(self):
        facts, resources = {"at-market"}, {"cash": 10.0}
        first = self.coordinator.replan(
            "npc-1", 1, facts, resources,
            {"repair": {"machine-fixed"}, "rest": {"rested"}},
            reason="repair required",
        )
        self.ledger.advance(
            first.execution_id, 2, facts, resources,
            interruption="temporary interruption",
        )
        with self.assertRaisesRegex(ValueError, "not currently feasible"):
            self.coordinator.resume_interrupted(
                first.execution_id, 3, facts, {"cash": 2.0},
                {"repair": {"machine-fixed"}, "rest": {"rested"}},
            )
        self.ledger.start(
            "parallel-owner-work", "npc-1", 3, "rest",
            {"safe-place"}, {"cash": 10.0}, plan_actions=("rest",),
        )
        with self.assertRaisesRegex(ValueError, "already has active work"):
            self.coordinator.resume_interrupted(
                first.execution_id, 4, facts, resources,
                {"repair": {"machine-fixed"}, "rest": {"rested"}},
            )


if __name__ == "__main__":
    unittest.main()
