"""Concrete checkpoint participant rollback integration tests."""
import tempfile
import unittest
from pathlib import Path

from simreality.model import NPC, NPCMemory, ActionTag, Description
from simreality.population_checkpoint_participants import build_population_transaction_participants
from simreality.population_transaction import PopulationTickTransactionCoordinator
from simreality.population_budget import PopulationBudgetController
from simreality.action_execution import ActionExecution, ActionExecutionLedger, ActionExecutionPolicy
from simreality.action_world_state import ActionWorldState
from simreality.inventory import ActionInventoryAdapter, ActionInventoryEffect, InventoryLedger
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.population_execution import NPCDecisionContext, PopulationExecutionLoop
from simreality.population_actions import NPCActionDispatchAdapter
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import RoutineBook, RoutineBlock
from simreality.simulation_tick import SimulationTickCoordinator
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger, SocialInteraction
from simreality.beliefs import Evidence
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger
from simreality.travel import TravelLedger, TravelJourney, TravelTickAdapter
from simreality.presence import PresenceLedger, PresenceTickAdapter
from simreality.presence_encounters import PresenceSocialAdapter
from simreality.household_economy import (
    EconomicAccount, EconomicLedger, EconomicTransfer, EconomicActionAdapter,
    ActionEconomicEffect, ActionHouseholdEffect, HouseholdActionAdapter, HouseholdLedger, HouseholdObligation,
)


class PopulationCheckpointParticipantTests(unittest.TestCase):
    def setUp(self):
        self.npcs = {"npc-a": NPC("npc-a"), "npc-b": NPC("npc-b")}
        self.events = WorldEventLedger()
        self.trust = SocialTrustLedger()
        self.beliefs = SocialBeliefSystem(self.trust)
        self.conversations = SocialConversationAdapter(self.trust, self.beliefs)
        self.memory = WorldEventMemoryAdapter(self.events)
        self.travel_ledger = TravelLedger()
        self.travel_adapter = TravelTickAdapter((), self.travel_ledger)
        self.presence_ledger = PresenceLedger()
        self.presence_adapter = PresenceTickAdapter(self.presence_ledger)
        self.encounters = PresenceSocialAdapter(self.presence_ledger)
        self.tick = SimulationTickCoordinator(self.events, self.memory, self.conversations)
        self.routines = RoutineBook()
        self.routine_executions = RoutineExecutionLedger()
        self.economics = EconomicLedger()
        self.economics.add_account(EconomicAccount("employer", "company", "business"), 100)
        self.economics.add_account(EconomicAccount("family", "npc-a", "household"), 0)
        self.economics.add_account(EconomicAccount("utility", "utility", "provider"), 0)
        self.households = HouseholdLedger(self.economics)
        self.households.add(HouseholdObligation(
            "bill-1", "npc-a", "family", "utility", 15, 1, "utility bill",
        ))
        self.goals = GoalBook()
        self.goals.add(NPCGoal("goal-work", "npc-a", "employment", priority=1.0))
        self.action_ledger = ActionExecutionLedger(
            DeterministicPlanner((PlanningAction("work", frozenset(), frozenset({"done"})),)),
            (ActionExecutionPolicy("work", goal_progress=(("goal-work", 0.25),)),),
            self.events, self.goals,
        )
        self.action_facts = {"available"}
        self.action_resources = {"energy": 8.0}
        self.action_world_state = ActionWorldState(
            {"npc-a": self.action_facts}, {"npc-a": self.action_resources},
        )
        self.inventory = InventoryLedger({
            ("store", "meal"): 20.0,
            ("npc-a", "meal"): 0.0,
        })
        self.inventory_actions = ActionInventoryAdapter(self.inventory, (
            ActionInventoryEffect("work", "ration", "meal", 1.0, "store", "npc-a", "work_ration"),
        ))
        self.economic_actions = EconomicActionAdapter(self.economics, (
            ActionEconomicEffect("work", "employer", "family", 20, "wage"),
        ))
        self.household_actions = HouseholdActionAdapter(self.households, (
            ActionHouseholdEffect(
                "work", "rent-contribution", "npc-a", "family", "utility",
                5.0, 1, "action-generated utility contribution",
            ),
        ))
        self.budget_controller = PopulationBudgetController(16.0)
        self.budget_controller.record_phase_sample("social", 8.0, 4)
        self.participants = build_population_transaction_participants(
            self.npcs, self.tick, self.routines, self.routine_executions,
            travel_adapter=self.travel_adapter,
            presence_adapter=self.presence_adapter,
            encounter_adapter=self.encounters,
            economic_action_adapter=self.economic_actions,
            household_ledger=self.households,
            action_ledger=self.action_ledger,
            action_world_state=self.action_world_state,
            household_action_adapter=self.household_actions,
            inventory_ledger=self.inventory,
            inventory_action_adapter=self.inventory_actions,
            population_budget_controller=self.budget_controller,
        )

    def test_concrete_participants_restore_npc_social_event_routine_and_economy_state(self):
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            before_names = transaction.participant_names
            self.assertTrue({
                "npcs", "world_events", "event_memory", "social_conversations",
                "social_trust", "social_beliefs", "routine_book", "routine_executions",
                "travel", "presence", "encounters", "action_executions", "action_goals",
                "economics", "economic_actions", "households", "action_world_state", "household_actions", "inventory", "inventory_actions", "population_budget",
            } <= before_names)

            def partially_apply_then_fail():
                npc = self.npcs["npc-a"]
                npc.personal_stress = 8.5
                npc.remember(NPCMemory(
                    "npc-a", "npc-b", 0.8, 0.9, 12.0,
                    ActionTag.CRIME_ASSAULT, Description(),
                ))
                self.events.append(WorldEventLedger.make_event(
                    "event-1", 1, "test_event", participants=("npc-a",),
                ))
                self.trust.add(SocialInteraction(
                    "trust-1", "npc-a", "npc-b", 1, 0.9, 1, "test",
                ))
                self.beliefs.observe("npc-a", Evidence(
                    "evidence-1", "claim-1", "npc-b", 1, 0.8, 0.5, 1,
                ))
                self.routines.add(RoutineBlock(
                    "routine-1", "npc-a", "work", "office", 480, 600,
                ))
                self.economics.transfer(EconomicTransfer(
                    "wage-1", 1, "employer", "family", 20, "work",
                ))
                self.economic_actions._applied["execution-1"] = self.economics.snapshot()[0]
                self.households.settle("bill-1", 1)
                self.action_facts.add("mutated")
                self.action_resources["energy"] = 0.0
                self.budget_controller.record_phase_sample("social", 80.0, 1)
                self.inventory_actions.apply_all(ActionExecution(
                    "inventory-test", "npc-a", 1, "work", "completed", "done",
                    (), (), (), (), "inventory-event",
                ), 1)
                raise RuntimeError("injected after economic phase")

            with self.assertRaisesRegex(RuntimeError, "injected after economic phase"):
                transaction.execute(1, {"tick": 1}, partially_apply_then_fail)

            self.assertEqual(self.npcs["npc-a"].personal_stress, 0.0)
            self.assertEqual(self.npcs["npc-a"].memories, [])
            self.assertEqual(self.events.snapshot(), ())
            self.assertEqual(self.memory.snapshot(), ())
            self.assertEqual(self.trust.snapshot(), ())
            self.assertEqual(self.beliefs.beliefs_for("npc-a"), ())
            self.assertEqual(self.routines.snapshot(), ())
            self.assertEqual(self.routine_executions.snapshot(), ())
            self.assertEqual(self.economics.balance("employer"), 100.0)
            self.assertEqual(self.economics.balance("family"), 0.0)
            self.assertEqual(self.economics.snapshot(), ())
            self.assertEqual(self.economic_actions._applied, {})
            self.assertEqual(self.households.snapshot()[0].status, "open")
            self.assertEqual(self.action_facts, {"available"})
            self.assertEqual(self.action_resources, {"energy": 8.0})
            self.assertEqual(self.budget_controller.subsystem_cost_ms("social"), 2.0)
            self.assertEqual(self.inventory.quantity("store", "meal"), 20.0)
            self.assertEqual(self.inventory.quantity("npc-a", "meal"), 0.0)
            self.assertEqual(self.inventory.snapshot(), ())

    def test_actual_social_phase_failure_rolls_back_witness_memory_and_replay_cache(self):
        event = WorldEventLedger.make_event(
            "witness-event", 1, "assault",
            participants=("npc-b",), witnesses=("npc-a",),
            attributes={
                "action_tag": ActionTag.CRIME_ASSAULT.value,
                "target_entity_id": "npc-b",
                "memory_impact": 0.75,
            },
        )
        self.events.append(event)
        observed = []
        def fail_after_social(phase, tick):
            observed.append((phase, tick))
            if phase == "social":
                raise RuntimeError("injected after actual social phase")
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            failing_loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                transaction_coordinator=transaction,
                phase_observer=fail_after_social,
            )
            with self.assertRaisesRegex(RuntimeError, "injected after actual social phase"):
                failing_loop.run_tick(
                    1, 500, self.npcs, event_ids=("witness-event",),
                    outcome_samples={},
                )
            self.assertIn(("social", 1), observed)
            self.assertEqual(self.npcs["npc-a"].memories, [])
            self.assertEqual(self.memory.snapshot(), ())
            self.assertEqual(self.events.get("witness-event"), event)

            retry_loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                transaction_coordinator=transaction,
            )
            retried = retry_loop.run_tick(
                1, 500, self.npcs, event_ids=("witness-event",),
                outcome_samples={},
            )
            self.assertEqual(len(retried.social.materialized_memories), 1)
            self.assertEqual(len(self.npcs["npc-a"].memories), 1)
            self.assertEqual(len(self.memory.snapshot()), 1)

    def test_actual_routine_phase_failure_rolls_back_execution_ledger_and_retries(self):
        self.routines.add(RoutineBlock(
            "routine-phase", "npc-a", "work", "office", 480, 600,
        ))
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            def fail_after_routines(phase, tick):
                if phase == "routines":
                    raise RuntimeError("injected after actual routine phase")
            failing_loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                transaction_coordinator=transaction,
                phase_observer=fail_after_routines,
            )
            with self.assertRaisesRegex(RuntimeError, "injected after actual routine phase"):
                failing_loop.run_tick(
                    1, 500, self.npcs, outcome_samples={"routine-phase": 0.4},
                )
            self.assertEqual(
                tuple(item.routine_id for item in self.routines.snapshot()),
                ("routine-phase",),
            )
            self.assertEqual(self.routine_executions.snapshot(), ())

            retry_loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                transaction_coordinator=transaction,
            )
            retried = retry_loop.run_tick(
                1, 500, self.npcs, outcome_samples={"routine-phase": 0.4},
            )
            self.assertEqual(
                tuple(item.routine_id for item in retried.routine_executions),
                ("routine-phase",),
            )
            self.assertEqual(len(self.routine_executions.snapshot()), 1)

    def test_population_tick_rolls_back_action_dispatch_facts_and_economy_after_failure(self):
        state = self.action_world_state
        dispatch = NPCActionDispatchAdapter(self.action_ledger)
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                decision_cycle=NPCDecisionCycle(self.goals, self.action_ledger.planner),
                transaction_coordinator=transaction,
                economic_action_adapter=self.economic_actions,
                household_ledger=self.households,
                action_execution_ledger=self.action_ledger,
                action_dispatch_adapter=dispatch,
                action_world_state=state,
                household_action_adapter=self.household_actions,
                inventory_action_adapter=self.inventory_actions,
            )
            context = {"npc-a": NPCDecisionContext(
                frozenset(), {"goal-work": frozenset({"done"})},
            )}
            started = loop.run_tick(1, 500, self.npcs, outcome_samples={}, decision_contexts=context)
            self.assertEqual(started.action_dispatches[0].status, "started")
            self.assertEqual(len(self.action_ledger.active()), 1)

            restarted_loop = PopulationExecutionLoop(
                self.tick, self.routines, self.routine_executions,
                decision_cycle=NPCDecisionCycle(self.goals, self.action_ledger.planner),
                transaction_coordinator=transaction,
                economic_action_adapter=self.economic_actions,
                household_ledger=self.households,
                action_execution_ledger=self.action_ledger,
                action_dispatch_adapter=NPCActionDispatchAdapter(self.action_ledger),
                action_world_state=state,
                household_action_adapter=self.household_actions,
                inventory_action_adapter=self.inventory_actions,
            )
            replayed_start = restarted_loop.run_tick(
                1, 500, self.npcs, outcome_samples={}, decision_contexts=context,
            )
            self.assertEqual(replayed_start.action_dispatches[0].status, "started")
            self.assertEqual(len(self.action_ledger.active()), 1)

            def fail_after_economy(phase, tick):
                if phase == "households":
                    raise RuntimeError("injected after actual household phase")
            restarted_loop.phase_observer = fail_after_economy
            with self.assertRaisesRegex(RuntimeError, "injected after actual household phase"):
                restarted_loop.run_tick(2, 501, self.npcs, outcome_samples={}, decision_contexts=context)

            self.assertEqual(len(self.action_ledger.active()), 1)
            self.assertEqual(self.action_ledger.active()[0].progress_ticks, 0)
            self.assertEqual(state.world_facts_by_owner["npc-a"], {"available"})
            self.assertEqual(state.resources_by_owner["npc-a"], {"energy": 8.0})
            self.assertEqual(self.economics.balance("employer"), 100.0)
            self.assertEqual(self.economics.snapshot(), ())
            self.assertEqual(tuple(item.obligation_id for item in self.households.snapshot()), ("bill-1",))
            self.assertEqual(self.household_actions._applied, {})
            self.assertEqual(self.inventory_actions._applied, {})
            restarted_loop.phase_observer = None

            retried = restarted_loop.run_tick(2, 501, self.npcs, outcome_samples={}, decision_contexts=context)
            self.assertEqual(retried.action_results[0].status, "completed")
            self.assertEqual(state.world_facts_by_owner["npc-a"], {"available", "done"})
            self.assertEqual(self.economics.balance("employer"), 80.0)
            self.assertEqual(self.economics.balance("family"), 20.0)
            self.assertEqual(len(retried.economic_transfers), 1)
            self.assertEqual(len(retried.inventory_transfers), 1)
            self.assertEqual(self.inventory.quantity("store", "meal"), 19.0)
            self.assertEqual(self.inventory.quantity("npc-a", "meal"), 1.0)
            self.assertEqual(len(retried.action_obligations), 1)
            self.assertEqual(retried.action_obligations[0].obligation_id, "action:npc:npc-a:tick:1:step:0:rent-contribution")

    def test_action_execution_ledger_and_its_world_events_rollback_together(self):
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            def execute_then_fail():
                result = self.action_ledger.execute(
                    "execution-1", "npc-a", 1, "work", set(), {},
                    plan_actions=("work",),
                )
                self.assertEqual(result.status, "completed")
                raise RuntimeError("action phase failure")
            with self.assertRaisesRegex(RuntimeError, "action phase failure"):
                transaction.execute(1, {"action": "work"}, execute_then_fail)
            self.assertIsNone(self.action_ledger.get("execution-1"))
            self.assertEqual(self.action_ledger.active(), ())
            self.assertEqual(self.goals.goals["goal-work"].progress, 0.0)
            self.assertEqual(self.events.snapshot(), ())

    def test_restart_rollback_restores_economic_household_and_inventory_replay_indexes(self):
        execution = ActionExecution(
            "execution-ledgers", "npc-a", 1, "work", "completed", "done",
            (), (), (), (), "event-ledgers",
        )
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            def apply_all_ledgers():
                wages = self.economic_actions.apply_all(execution, 1)
                obligations = self.household_actions.apply_all(execution, 1)
                inventory = self.inventory_actions.apply_all(execution, 1)
                return (len(wages), len(obligations), len(inventory))
            self.assertEqual(transaction.execute(1, {"apply": "all"}, apply_all_ledgers), (1, 1, 1))
            balances = self.economics.account_snapshot()
            obligations = self.households.snapshot()
            stock = self.inventory.stock_snapshot()

            def corrupt_then_fail():
                self.economic_actions._applied.clear()
                self.household_actions._applied.clear()
                self.inventory_actions._applied.clear()
                self.economics._transfers.clear()
                self.households._obligations.clear()
                self.inventory._transfers.clear()
                self.inventory._stock.clear()
                raise RuntimeError("restart recovery injection")
            with self.assertRaisesRegex(RuntimeError, "restart recovery injection"):
                transaction.execute(2, {"apply": "corrupt"}, corrupt_then_fail)

            self.assertEqual(self.economics.account_snapshot(), balances)
            self.assertEqual(self.households.snapshot(), obligations)
            self.assertEqual(self.inventory.stock_snapshot(), stock)
            self.assertEqual(self.economic_actions.apply_all(execution, 1), tuple(
                item for item in self.economics.snapshot()
                if item.transfer_id.startswith("action:execution-ledgers:")
            ))
            self.assertEqual(self.household_actions.apply_all(execution, 1), tuple(
                item for item in obligations if item.obligation_id.startswith("action:")
            ))
            self.assertEqual(self.inventory_actions.apply_all(execution, 1), tuple(
                item for item in self.inventory.snapshot()
                if item.transfer_id.startswith("action:execution-ledgers:")
            ))

    def test_concrete_participant_restore_preserves_live_object_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            npc_ref = self.npcs["npc-a"]
            event_ref = self.events
            trust_ref = self.trust
            beliefs_ref = self.beliefs
            transaction.execute(1, {"tick": 1}, lambda: self.events.append(
                WorldEventLedger.make_event("event-1", 1, "committed")
            ))
            self.assertIs(self.npcs["npc-a"], npc_ref)
            self.assertIs(self.events, event_ref)
            self.assertIs(self.conversations.trust, trust_ref)
            self.assertIs(self.conversations.beliefs, beliefs_ref)


    def test_failure_after_each_population_phase_restores_all_registered_subsystems(self):
        with tempfile.TemporaryDirectory() as directory:
            transaction = PopulationTickTransactionCoordinator(
                Path(directory) / "population.json", self.participants,
            )
            for failed_phase in range(8):
                tick = 10 + failed_phase
                memory = NPCMemory(
                    "npc-a", "npc-b", 0.7, 0.8, float(tick),
                    ActionTag.CRIME_ASSAULT, Description(),
                )
                phases = (
                    lambda: setattr(self.npcs["npc-a"], "personal_stress", float(tick)),
                    lambda: (
                        self.events.append(WorldEventLedger.make_event(
                            f"event-{tick}", tick, "phase_event", participants=("npc-a",),
                        )),
                        self.memory._processed.__setitem__((f"event-{tick}", "npc-a"), memory),
                        self.npcs["npc-a"].remember(memory),
                    ),
                    lambda: self.trust.add(SocialInteraction(
                        f"trust-{tick}", "npc-a", "npc-b", 1, 0.7, tick, "phase-test",
                    )),
                    lambda: self.beliefs.observe("npc-a", Evidence(
                        f"evidence-{tick}", f"claim-{tick}", "npc-b", 1, 0.8, 0.5, tick,
                    )),
                    lambda: self.routines.add(RoutineBlock(
                        f"routine-{tick}", "npc-a", "work", "office", 480, 600,
                    )),
                    lambda: self.travel_ledger.add(TravelJourney(
                        f"journey-{tick}", "npc-a", "origin", "destination",
                        ("origin", "destination"), ("edge",), started_tick=tick,
                    )),
                    lambda: (
                        self.presence_ledger.place("npc-a", "market", tick),
                        self.presence_ledger.place("npc-b", "market", tick),
                        self.encounters.encounter(
                            f"encounter-{tick}", "npc-a", "npc-b", tick,
                            opportunity=True, events=self.events,
                        ),
                    ),
                    lambda: (
                        self.economics.transfer(EconomicTransfer(
                            f"transfer-{tick}", tick, "employer", "family", 20, "phase-test",
                        )),
                        self.economic_actions._applied.__setitem__(
                            f"execution-{tick}", self.economics.snapshot()[-1],
                        ),
                        self.households.settle("bill-1", tick),
                    ),
                )
                def fail_at_boundary():
                    for phase_index, phase in enumerate(phases):
                        phase()
                        if phase_index == failed_phase:
                            raise RuntimeError(f"injected failure after phase {phase_index}")
                with self.assertRaisesRegex(RuntimeError, f"phase {failed_phase}"):
                    transaction.execute(tick, {"tick": tick, "fail_after": failed_phase}, fail_at_boundary)
                self.assertEqual(self.npcs["npc-a"].personal_stress, 0.0)
                self.assertEqual(self.npcs["npc-a"].memories, [])
                self.assertEqual(self.events.snapshot(), ())
                self.assertEqual(self.memory.snapshot(), ())
                self.assertEqual(self.trust.snapshot(), ())
                self.assertEqual(self.beliefs.beliefs_for("npc-a"), ())
                self.assertEqual(self.routines.snapshot(), ())
                self.assertEqual(self.economics.balance("employer"), 100.0)
                self.assertEqual(self.economics.balance("family"), 0.0)
                self.assertEqual(self.economics.snapshot(), ())
                self.assertEqual(self.economic_actions._applied, {})
                self.assertEqual(self.households.snapshot()[0].status, "open")
                self.assertEqual(self.travel_ledger.snapshot(), ())
                self.assertEqual(self.presence_ledger.snapshot(), ())
                self.assertEqual(self.encounters.ledger.snapshot(), ())

if __name__ == "__main__":
    unittest.main()
