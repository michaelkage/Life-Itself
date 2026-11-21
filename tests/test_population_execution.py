"""Population execution loop integration tests."""
import unittest

from simreality.model import NPC
from simreality.action_execution import ActionExecution
from simreality.household_economy import EconomicAccount, EconomicLedger, EconomicActionAdapter, ActionEconomicEffect, HouseholdLedger, HouseholdObligation
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.population_execution import NPCDecisionContext, PopulationExecutionLoop
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import RoutineBlock, RoutineBook
from simreality.simulation_tick import SimulationTickCoordinator
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger


class PopulationExecutionLoopTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        trust = SocialTrustLedger()
        conversations = SocialConversationAdapter(trust, SocialBeliefSystem(trust))
        coordinator = SimulationTickCoordinator(
            self.events, WorldEventMemoryAdapter(self.events), conversations,
        )
        self.book = RoutineBook((
            RoutineBlock("work-a", "npc-a", "work", "office", 480, 960),
            RoutineBlock("rest-b", "npc-b", "rest", "home", 480, 960),
        ))
        self.ledger = RoutineExecutionLedger()
        self.loop = PopulationExecutionLoop(coordinator, self.book, self.ledger)
        self.npcs = {"npc-b": NPC("npc-b"), "npc-a": NPC("npc-a")}

    def test_executes_roster_in_stable_order_and_resolves_due_routines(self):
        result = self.loop.run_tick(
            1, 500, self.npcs, outcome_samples={"work-a": 0.2, "rest-b": 0.7},
        )
        self.assertEqual(result.processed_npc_ids, ("npc-a", "npc-b"))
        self.assertEqual(
            tuple(item.routine_id for item in result.routine_executions),
            ("rest-b", "work-a"),
        )
        self.assertEqual(result.tick, 1)

    def test_population_tick_replay_returns_original_result(self):
        request = {"outcome_samples": {"work-a": 0.2, "rest-b": 0.7}}
        first = self.loop.run_tick(1, 500, self.npcs, **request)
        second = self.loop.run_tick(1, 500, self.npcs, **request)
        self.assertIs(first, second)
        self.assertEqual(len(self.ledger.snapshot()), 2)

    def test_conflicting_population_replay_is_rejected(self):
        self.loop.run_tick(
            1, 500, self.npcs, outcome_samples={"work-a": 0.2, "rest-b": 0.7},
        )
        with self.assertRaisesRegex(ValueError, "replayed with different inputs"):
            self.loop.run_tick(
                1, 500, self.npcs, outcome_samples={"work-a": 0.8, "rest-b": 0.7},
            )

    def test_missing_sample_fails_before_world_tick_is_committed(self):
        with self.assertRaisesRegex(ValueError, "missing outcome sample"):
            self.loop.run_tick(1, 500, self.npcs, outcome_samples={"work-a": 0.2})
        self.assertEqual(self.loop.coordinator.snapshot(), ())
        self.assertEqual(self.ledger.snapshot(), ())

    def test_population_slice_can_select_a_subset_of_owners(self):
        result = self.loop.run_tick(
            1, 500, self.npcs,
            outcome_samples={"work-a": 0.2},
            owner_ids=("npc-a",),
        )
        self.assertEqual(tuple(item.routine_id for item in result.routine_executions), ("work-a",))
        self.assertEqual(result.processed_npc_ids, ("npc-a", "npc-b"))


    def test_runs_explicit_read_only_npc_decisions_in_stable_order(self):
        goals = GoalBook()
        goals.add(NPCGoal("goal-a", "npc-a", "security", priority=5))
        goals.add(NPCGoal("goal-b", "npc-b", "rest", priority=5))
        planner = DeterministicPlanner((
            PlanningAction("earn", frozenset({"available"}), frozenset({"paid"})),
            PlanningAction("rest", frozenset({"available"}), frozenset({"rested"})),
        ))
        loop = PopulationExecutionLoop(
            self.loop.coordinator, self.book, self.ledger,
            decision_cycle=NPCDecisionCycle(goals, planner),
        )
        result = loop.run_tick(
            1, 500, self.npcs,
            outcome_samples={"work-a": 0.2, "rest-b": 0.7},
            decision_contexts={
                "npc-b": NPCDecisionContext(frozenset({"available"}), {"goal-b": frozenset({"rested"})}),
                "npc-a": NPCDecisionContext(frozenset({"available"}), {"goal-a": frozenset({"paid"})}),
            },
        )
        self.assertEqual(tuple(item.owner_id for item in result.decisions), ("npc-a", "npc-b"))
        self.assertTrue(all(item.actionable for item in result.decisions))
        self.assertEqual(result.decisions[0].plan.actions, ("earn",))

    def test_decision_context_requires_configured_cycle(self):
        with self.assertRaisesRegex(ValueError, "require an NPCDecisionCycle"):
            self.loop.run_tick(
                1, 500, self.npcs,
                outcome_samples={"work-a": 0.2, "rest-b": 0.7},
                decision_contexts={
                    "npc-a": NPCDecisionContext(frozenset({"available"}), {}),
                },
            )

    def test_unknown_owner_fails_before_world_tick_is_committed(self):
        with self.assertRaisesRegex(KeyError, "absent from population"):
            self.loop.run_tick(
                1, 500, self.npcs,
                outcome_samples={},
                owner_ids=("not-present",),
            )
        self.assertEqual(self.loop.coordinator.snapshot(), ())


    def test_completed_action_wage_and_household_settlement_share_population_tick(self):
        economics = EconomicLedger((
            EconomicAccount("employer", "company", "business"),
            EconomicAccount("household", "family", "household"),
            EconomicAccount("utility", "utility", "provider"),
        ))
        economics._balances.update({"employer": 100.0, "household": 0.0, "utility": 0.0})
        household = HouseholdLedger(economics)
        household.add(HouseholdObligation("rent-1", "family", "household", "utility", 10.0, 1, "utility bill"))
        adapter = EconomicActionAdapter(economics, (
            ActionEconomicEffect("work-shift", "employer", "household", 20.0, "wage"),
        ))
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            economic_action_adapter=adapter, household_ledger=household,
        )
        completed = ActionExecution(
            "action-1", "npc-a", 1, "work-shift", "completed", "shift completed",
            (), (), (), (), "action-event-1",
        )
        result = loop.run_tick(
            1, 500, self.npcs, outcome_samples={},
            completed_action_executions=(completed,), household_settlement_ids=("rent-1",),
        )
        self.assertEqual(len(result.economic_transfers), 1)
        self.assertEqual(result.economic_transfers[0].reference, "action:action-1:wage")
        self.assertEqual(len(result.household_settlements), 1)
        self.assertEqual(economics.balance("employer"), 80.0)
        self.assertEqual(economics.balance("household"), 10.0)
        self.assertEqual(economics.balance("utility"), 10.0)

if __name__ == "__main__":
    unittest.main()
