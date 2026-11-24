import unittest

from simreality.action_execution import ActionExecutionLedger, ActionExecutionPolicy
from simreality.npc_autonomy import NPCDecision
from simreality.planning import DeterministicPlanner, PlanningAction, PlanResult
from simreality.population_actions import NPCActionDispatchAdapter


class PopulationActionDispatchTests(unittest.TestCase):
    def setUp(self):
        planner = DeterministicPlanner((
            PlanningAction("earn", frozenset({"available"}), frozenset({"paid"})),
            PlanningAction("rest", frozenset({"home"}), frozenset({"rested"})),
        ))
        self.ledger = ActionExecutionLedger(
            planner, (ActionExecutionPolicy("earn", resource_costs=(("energy", 2.0),)),),
        )
        self.adapter = NPCActionDispatchAdapter(self.ledger)
        self.decision = NPCDecision(
            "npc-a", 3, "goal-a", "work",
            PlanResult(True, ("earn",), 1, 1, "plan found"), "plan found",
        )

    def test_dispatch_starts_first_step_after_live_validation(self):
        facts = {"npc-a": {"available"}}
        resources = {"npc-a": {"energy": 5.0}}
        result = self.adapter.dispatch(3, (self.decision,), facts, resources)
        self.assertEqual(result[0].status, "started")
        self.assertEqual(result[0].action_id, "earn")
        self.assertEqual(result[0].active.reserved_resources, (("energy", 2.0),))

    def test_live_preconditions_are_revalidated(self):
        with self.assertRaisesRegex(ValueError, "preconditions are not satisfied"):
            self.adapter.dispatch(3, (self.decision,), {"npc-a": set()}, {"npc-a": {"energy": 5.0}})
        self.assertEqual(self.ledger.active(), ())

    def test_insufficient_resources_reject_dispatch(self):
        with self.assertRaisesRegex(ValueError, "insufficient unreserved resource"):
            self.adapter.dispatch(3, (self.decision,), {"npc-a": {"available"}}, {"npc-a": {"energy": 1.0}})
        self.assertEqual(self.ledger.active(), ())

    def test_dispatch_replay_is_idempotent(self):
        args = (3, (self.decision,), {"npc-a": {"available"}}, {"npc-a": {"energy": 5.0}})
        first = self.adapter.dispatch(*args)
        second = self.adapter.dispatch(*args)
        self.assertEqual(first, second)
        self.assertEqual(len(self.ledger.active()), 1)

    def test_non_actionable_decision_is_not_executed(self):
        decision = NPCDecision("npc-a", 3, None, None, None, "no actionable goal")
        result = self.adapter.dispatch(3, (decision,), {}, {})
        self.assertEqual(result[0].status, "not_dispatched")
        self.assertEqual(self.ledger.active(), ())


if __name__ == "__main__":
    unittest.main()
