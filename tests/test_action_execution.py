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
            plan_actions=("buy-tools",),
        )
        second = self.ledger.execute(
            "tick-2:repair-bike", "npc-1", 2, "repair-bike", facts, resources,
            plan_actions=("buy-tools", "repair-bike"), action_index=1,
        )
        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertIn("bike-fixed", facts)


if __name__ == "__main__":
    unittest.main()
