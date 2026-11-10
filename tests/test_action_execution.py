import unittest

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger


class ActionExecutionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.planner = DeterministicPlanner((
            PlanningAction("buy-tools", frozenset({"at-shop"}),
                           frozenset({"has-tools"}), cost=2),
            PlanningAction("repair-bike", frozenset({"has-tools"}),
                           frozenset({"bike-fixed"})),
        ))
        self.events = WorldEventLedger()
        self.ledger = ActionExecutionLedger(
            self.planner,
            (ActionExecutionPolicy("buy-tools", (("cash", 5.0),)),),
            self.events,
        )

    def test_executes_one_action_and_updates_facts_and_resources(self):
        facts = {"at-shop"}
        resources = {"cash": 8.0}
        result = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources,
            plan_actions=("buy-tools",),
        )
        self.assertEqual(result.status, "completed")
        self.assertEqual(facts, {"at-shop", "has-tools"})
        self.assertEqual(resources, {"cash": 3.0})
        self.assertEqual(self.events.get(result.event_id).event_type,
                         "npc_action_execution")

    def test_rechecks_live_preconditions_and_does_not_mutate_on_block(self):
        facts = set()
        resources = {"cash": 8.0}
        result = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources,
            plan_actions=("buy-tools",),
        )
        self.assertEqual(result.status, "blocked")
        self.assertEqual(facts, set())
        self.assertEqual(resources, {"cash": 8.0})

    def test_insufficient_resources_blocks_action(self):
        facts = {"at-shop"}
        resources = {"cash": 4.0}
        result = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources,
            plan_actions=("buy-tools",),
        )
        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.reason, "insufficient resources")
        self.assertEqual(facts, {"at-shop"})
        self.assertEqual(resources, {"cash": 4.0})

    def test_explicit_interruption_records_without_applying_effects(self):
        facts = {"at-shop"}
        resources = {"cash": 8.0}
        result = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources, plan_actions=("buy-tools",),
            interruption="shop closed unexpectedly",
        )
        self.assertEqual(result.status, "interrupted")
        self.assertEqual(facts, {"at-shop"})
        self.assertEqual(resources, {"cash": 8.0})

    def test_execution_replay_is_idempotent_and_conflicts_are_rejected(self):
        facts = {"at-shop"}
        resources = {"cash": 8.0}
        first = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources,
            plan_actions=("buy-tools",),
        )
        replay = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools",
            {"at-shop"}, {"cash": 8.0},
            plan_actions=("buy-tools",),
        )
        self.assertEqual(first, replay)
        self.assertEqual(resources, {"cash": 3.0})
        with self.assertRaisesRegex(ValueError, "conflicting action execution ID"):
            self.ledger.execute(
                "tick-1:buy-tools", "npc-1", 1, "buy-tools",
                {"at-shop"}, {"cash": 7.0},
                plan_actions=("buy-tools",),
            )

    def test_distinct_actions_can_advance_the_same_plan(self):
        facts = {"at-shop"}
        resources = {"cash": 8.0}
        first = self.ledger.execute(
            "tick-1:buy-tools", "npc-1", 1, "buy-tools", facts, resources,
            plan_actions=("buy-tools", "repair-bike"),
        )
        second = self.ledger.execute(
            "tick-2:repair-bike", "npc-1", 2, "repair-bike", facts, resources,
            plan_actions=("buy-tools", "repair-bike"), action_index=1,
        )
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertIn("bike-fixed", facts)



    def test_multitick_execution_reserves_then_consumes_resources_on_completion(self):
        policy = ActionExecutionPolicy("buy-tools", (("cash", 5.0),), duration_ticks=2)
        ledger = ActionExecutionLedger(self.planner, (policy,), self.events)
        facts, resources = {"at-shop"}, {"cash": 8.0}
        started = ledger.start("multi-1", "npc-1", 1, "buy-tools", facts, resources,
                               plan_actions=("buy-tools",))
        self.assertEqual(started.progress_ticks, 0)
        self.assertEqual(resources["cash"], 8.0)
        self.assertEqual(ledger._reserved("cash"), 5.0)
        progressed = ledger.advance("multi-1", 2, facts, resources)
        self.assertEqual(progressed.progress_ticks, 1)
        self.assertEqual(ledger.advance("multi-1", 2, facts, resources), progressed)
        self.assertEqual(resources["cash"], 8.0)
        completed = ledger.advance("multi-1", 3, facts, resources)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(facts, {"at-shop", "has-tools"})
        self.assertEqual(resources["cash"], 3.0)
        self.assertEqual(ledger._reserved("cash"), 0.0)

    def test_interruption_releases_reservation_without_applying_effects(self):
        ledger = ActionExecutionLedger(
            self.planner,
            (ActionExecutionPolicy("buy-tools", (("cash", 5.0),), duration_ticks=3),),
            self.events,
        )
        facts, resources = {"at-shop"}, {"cash": 8.0}
        ledger.start("multi-interrupt", "npc-1", 1, "buy-tools", facts, resources,
                     plan_actions=("buy-tools",))
        result = ledger.advance("multi-interrupt", 2, facts, resources,
                                interruption="shop closed")
        self.assertEqual(result.status, "interrupted")
        self.assertEqual(facts, {"at-shop"})
        self.assertEqual(resources, {"cash": 8.0})
        self.assertEqual(ledger._reserved("cash"), 0.0)

    def test_cancel_releases_reservation(self):
        ledger = ActionExecutionLedger(
            self.planner,
            (ActionExecutionPolicy("buy-tools", (("cash", 5.0),), duration_ticks=2),),
            self.events,
        )
        facts, resources = {"at-shop"}, {"cash": 8.0}
        ledger.start("multi-cancel", "npc-1", 1, "buy-tools", facts, resources,
                     plan_actions=("buy-tools",))
        result = ledger.cancel("multi-cancel", 2, "NPC changed priorities")
        self.assertEqual(result.status, "cancelled")
        self.assertEqual(ledger._reserved("cash"), 0.0)
        self.assertEqual(resources, {"cash": 8.0})

    def test_active_execution_restores_from_snapshot_and_resumes(self):
        policy = ActionExecutionPolicy("buy-tools", (("cash", 5.0),), duration_ticks=2)
        ledger = ActionExecutionLedger(self.planner, (policy,), self.events)
        facts, resources = {"at-shop"}, {"cash": 8.0}
        ledger.start("restore-1", "npc-1", 1, "buy-tools", facts, resources,
                     plan_actions=("buy-tools",))
        ledger.advance("restore-1", 2, facts, resources)
        restored = ActionExecutionLedger.from_json(
            self.planner, (policy,), self.events, ledger.to_json()
        )
        self.assertEqual(restored.active("restore-1").progress_ticks, 1)
        self.assertEqual(restored.to_json(), ledger.to_json())
        result = restored.advance("restore-1", 3, facts, resources)
        self.assertEqual(result.status, "completed")
        self.assertEqual(resources["cash"], 3.0)

    def test_snapshot_roundtrips_completed_execution_history(self):
        facts, resources = {"at-shop"}, {"cash": 8.0}
        self.ledger.execute("snapshot-done", "npc-1", 1, "buy-tools",
                            facts, resources, plan_actions=("buy-tools",))
        restored = ActionExecutionLedger.from_json(
            self.planner, (ActionExecutionPolicy("buy-tools", (("cash", 5.0),)),),
            self.events, self.ledger.to_json()
        )
        self.assertEqual(restored.snapshot(), self.ledger.snapshot())

    def test_completion_advances_linked_goal_progress_once(self):
        from simreality.goals import GoalBook, NPCGoal
        goals = GoalBook()
        goals.add(NPCGoal("repair", "npc-1", "personal", 1.0))
        policy = ActionExecutionPolicy("repair-bike", goal_progress=(("repair", 0.25),))
        ledger = ActionExecutionLedger(self.planner, (policy,), self.events, goals)
        facts, resources = {"has-tools"}, {}
        result = ledger.execute("goal-progress-1", "npc-1", 4, "repair-bike",
                                facts, resources, plan_actions=("repair-bike",))
        self.assertEqual(result.status, "completed")
        self.assertEqual(goals.goals["repair"].progress, 0.25)
        self.assertEqual(ledger.execute("goal-progress-1", "npc-1", 4, "repair-bike",
                                        {"has-tools"}, {}, plan_actions=("repair-bike",)), result)
        self.assertEqual(goals.goals["repair"].progress, 0.25)


if __name__ == "__main__":
    unittest.main()
