"""Population execution loop integration tests."""
import unittest
import json
import tempfile
from pathlib import Path

from simreality.model import NPC, ActionTag
from simreality.action_execution import ActionExecution, ActionExecutionLedger, ActionExecutionPolicy
from simreality.action_world_state import ActionWorldState
from simreality.inventory import ActionInventoryAdapter, ActionInventoryEffect, InventoryLedger
from simreality.population_actions import NPCActionDispatchAdapter
from simreality.household_economy import EconomicAccount, EconomicLedger, EconomicActionAdapter, ActionEconomicEffect, ActionHouseholdEffect, HouseholdActionAdapter, HouseholdLedger, HouseholdObligation
from simreality.inventory import ActionInventoryAdapter, ActionInventoryEffect, InventoryLedger
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.population_execution import NPCDecisionContext, PopulationExecutionLoop
from simreality.population_lod_policy import default_population_lod_policy
from simreality.population_spatial import PopulationLOD, PopulationSchedule, PopulationSlice
from simreality.population_transaction import PopulationTickTransactionCoordinator, TransactionParticipant
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

    def test_lod_schedule_dispatches_each_subsystem_to_its_own_owner_batch(self):
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
        schedule = PopulationSchedule(
            1,
            (
                PopulationSlice("cell-a", PopulationLOD.FULL, ("npc-a",)),
                PopulationSlice("cell-b", PopulationLOD.DORMANT, ("npc-b",)),
            ),
            ("npc-a",), ("npc-b",),
        )
        subsystem_plan = {
            item.subsystem_id: item.owner_ids
            for item in schedule.subsystem_slices(default_population_lod_policy())
        }
        self.assertEqual(subsystem_plan["decision"], ("npc-a",))
        self.assertEqual(subsystem_plan["routine"], ("npc-a",))
        result = loop.run_tick(
            1, 500, self.npcs,
            outcome_samples={"work-a": 0.2},
            decision_contexts={
                "npc-a": NPCDecisionContext(frozenset({"available"}), {"goal-a": frozenset({"paid"})}),
                "npc-b": NPCDecisionContext(frozenset({"available"}), {"goal-b": frozenset({"rested"})}),
            },
            population_schedule=schedule,
            lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(tuple(item.owner_id for item in result.decisions), ("npc-a",))
        self.assertEqual(tuple(item.routine_id for item in result.routine_executions), ("work-a",))
        self.assertEqual(result.processed_npc_ids, ("npc-a", "npc-b"))

    def test_active_action_advancement_uses_action_subsystem_owner_batch(self):
        planner = DeterministicPlanner((
            PlanningAction("work", frozenset({"available"}), frozenset({"done"})),
        ))
        ledger = ActionExecutionLedger(
            planner, (ActionExecutionPolicy("work", duration_ticks=3),),
            events=self.events,
        )
        for owner in ("npc-a", "npc-b"):
            ledger.start(
                f"execution-{owner}", owner, 0, "work",
                {"available"}, {}, plan_actions=("work",),
            )
        state = ActionWorldState(
            {"npc-a": {"available"}, "npc-b": {"available"}},
            {"npc-a": {}, "npc-b": {}},
        )
        adapter = NPCActionDispatchAdapter(ledger)
        advanced = adapter.advance_active(1, state, owner_ids=("npc-a",))
        self.assertEqual(tuple(item.owner_id for item in advanced), ("npc-a",))
        progress = {item.owner_id: item.progress_ticks for item in ledger.active()}
        self.assertEqual(progress, {"npc-a": 1, "npc-b": 0})

    def test_deferred_event_memory_is_materialized_per_due_witness_without_blocking_others(self):
        event = WorldEventLedger.make_event(
            "deferred-memory", 1, "assault",
            participants=("npc-b",), witnesses=("npc-a", "npc-b"),
            attributes={
                "action_tag": ActionTag.CRIME_ASSAULT.value,
                "target_entity_id": "npc-b",
            },
        )
        self.events.append(event)
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
        )

        def schedule(tick):
            return PopulationSchedule(
                tick,
                (
                    PopulationSlice("cell-a", PopulationLOD.BACKGROUND, ("npc-a",)),
                    PopulationSlice("cell-b", PopulationLOD.DORMANT, ("npc-b",)),
                ),
                ("npc-a",), ("npc-b",),
            )

        first = loop.run_tick(
            1, 500, self.npcs, outcome_samples={}, event_ids=("deferred-memory",),
            population_schedule=schedule(1), lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(first.social.materialized_memories, ())
        self.assertEqual(self.npcs["npc-a"].memories, [])
        self.assertEqual(self.npcs["npc-b"].memories, [])

        later = loop.run_tick(
            4, 500, self.npcs, outcome_samples={},
            population_schedule=schedule(4), lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(
            tuple((event_id, witness_id) for event_id, witness_id, memory in later.social.materialized_memories),
            (("deferred-memory", "npc-a"),),
        )
        self.assertEqual(len(self.npcs["npc-a"].memories), 1)
        self.assertEqual(self.npcs["npc-b"].memories, [])
        self.assertTrue(loop.coordinator.memory_adapter.has_materialized("deferred-memory", "npc-a"))
        self.assertFalse(loop.coordinator.memory_adapter.has_materialized("deferred-memory", "npc-b"))

    def test_lod_schedule_must_cover_exact_population_roster(self):
        schedule = PopulationSchedule(
            1,
            (PopulationSlice("cell-a", PopulationLOD.FULL, ("npc-a",)),),
            ("npc-a",), (),
        )
        with self.assertRaisesRegex(ValueError, "exact NPC roster"):
            self.loop.run_tick(
                1, 500, self.npcs, outcome_samples={},
                population_schedule=schedule,
                lod_policy=default_population_lod_policy(),
            )

    def test_completed_action_economy_effect_waits_for_background_lod_cadence(self):
        economics = EconomicLedger((
            EconomicAccount("employer", "business", "business"),
            EconomicAccount("household", "npc-a", "household"),
        ))
        economics._balances.update({"employer": 50.0, "household": 0.0})
        economic_actions = EconomicActionAdapter(economics, (
            ActionEconomicEffect("earn", "employer", "household", 10.0, "wage"),
        ))
        action_ledger = ActionExecutionLedger(
            DeterministicPlanner((
                PlanningAction("earn", frozenset({"available"}), frozenset({"paid"})),
            )),
            (ActionExecutionPolicy("earn", duration_ticks=1),),
            events=self.events,
        )
        action_ledger.start(
            "execution-background", "npc-a", 0, "earn",
            {"available"}, {}, plan_actions=("earn",),
        )
        completed = action_ledger.advance("execution-background", 1, {"available"}, {})
        self.assertEqual(completed.status, "completed")
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            economic_action_adapter=economic_actions,
            action_execution_ledger=action_ledger,
        )
        def background_schedule(tick):
            return PopulationSchedule(
                tick,
                (
                    PopulationSlice("cell-a", PopulationLOD.BACKGROUND, ("npc-a",)),
                    PopulationSlice("cell-b", PopulationLOD.DORMANT, ("npc-b",)),
                ),
                ("npc-a",), ("npc-b",),
            )
        first = loop.run_tick(
            1, 500, self.npcs, outcome_samples={},
            population_schedule=background_schedule(1),
            lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(first.economic_transfers, ())
        self.assertEqual(economics.balance("employer"), 50.0)
        later = loop.run_tick(
            4, 500, self.npcs, outcome_samples={},
            population_schedule=background_schedule(4),
            lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(len(later.economic_transfers), 1)
        self.assertEqual(
            tuple(item.execution_id for item in later.action_results),
            ("execution-background",),
        )
        self.assertEqual(economics.balance("employer"), 40.0)
        self.assertEqual(economics.balance("household"), 10.0)

        settled_replay = loop.run_tick(
            8, 500, self.npcs, outcome_samples={},
            population_schedule=background_schedule(8),
            lod_policy=default_population_lod_policy(),
        )
        self.assertEqual(settled_replay.economic_transfers, ())
        self.assertEqual(settled_replay.action_results, ())

    def test_untransactional_economic_household_and_inventory_effects_replay_outputs_once(self):
        economics = EconomicLedger((
            EconomicAccount("employer", "business", "business"),
            EconomicAccount("household", "family", "household"),
            EconomicAccount("landlord", "landlord", "receivable"),
        ))
        economics._balances.update({"employer": 100.0, "household": 0.0, "landlord": 0.0})
        households = HouseholdLedger(economics)
        economic_actions = EconomicActionAdapter(economics, (
            ActionEconomicEffect("work", "employer", "household", 20.0, "wage"),
        ))
        household_actions = HouseholdActionAdapter(households, (
            ActionHouseholdEffect(
                "work", "rent", "family", "household", "landlord",
                5.0, 2, "rent obligation",
            ),
        ))
        inventory = InventoryLedger({("store", "ration"): 10.0, ("npc-a", "ration"): 0.0})
        inventory_actions = ActionInventoryAdapter(inventory, (
            ActionInventoryEffect(
                "work", "ration", "ration", 1.0, "store", "npc-a", "ration_award",
            ),
        ))
        completed = ActionExecution(
            "untransactional-effects", "npc-a", 1, "work", "completed", "done",
            (), (), (), (), "event-untransactional-effects",
        )
        def fail_after_inventory(phase, tick):
            if phase == "inventory":
                raise RuntimeError("after inventory effects")
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            economic_action_adapter=economic_actions,
            household_ledger=households,
            household_action_adapter=household_actions,
            inventory_action_adapter=inventory_actions,
            phase_observer=fail_after_inventory,
        )
        request = {
            "outcome_samples": {},
            "completed_action_executions": (completed,),
        }
        with self.assertRaisesRegex(RuntimeError, "after inventory effects"):
            loop.run_tick(4, 500, self.npcs, **request)

        self.assertEqual(economics.balance("employer"), 80.0)
        self.assertEqual(economics.balance("household"), 20.0)
        self.assertEqual(inventory.quantity("store", "ration"), 9.0)
        self.assertEqual(inventory.quantity("npc-a", "ration"), 1.0)
        self.assertEqual(len(households.snapshot()), 1)

        loop.phase_observer = None
        retried = loop.run_tick(4, 500, self.npcs, **request)
        self.assertEqual(len(retried.economic_transfers), 1)
        self.assertEqual(len(retried.action_obligations), 1)
        self.assertEqual(len(retried.inventory_transfers), 1)
        self.assertEqual(
            tuple(item.execution_id for item in retried.action_results),
            ("untransactional-effects",),
        )
        self.assertEqual(economics.balance("employer"), 80.0)
        self.assertEqual(economics.balance("household"), 20.0)
        self.assertEqual(len(economics.snapshot()), 1)
        self.assertEqual(len(inventory.snapshot()), 1)
        self.assertEqual(len(households.snapshot()), 1)

    def test_untransactional_household_phase_retry_reconstructs_all_action_effect_outputs(self):
        economics = EconomicLedger((
            EconomicAccount("employer", "business", "business"),
            EconomicAccount("household", "npc-a", "household"),
            EconomicAccount("landlord", "property-owner", "business"),
        ))
        economics._balances.update({
            "employer": 50.0, "household": 0.0, "landlord": 0.0,
        })
        economic_actions = EconomicActionAdapter(economics, (
            ActionEconomicEffect("earn", "employer", "household", 10.0, "wage"),
        ))
        households = HouseholdLedger(economics)
        household_actions = HouseholdActionAdapter(households, (
            ActionHouseholdEffect(
                "earn", "rent", "home-a", "household", "landlord",
                5.0, 1, "rent obligation",
            ),
        ))
        inventory = InventoryLedger({("store", "meal"): 1.0, ("npc-a", "meal"): 0.0})
        inventory_actions = ActionInventoryAdapter(inventory, (
            ActionInventoryEffect(
                "earn", "ration", "meal", 1.0, "store", "npc-a", "ration",
            ),
        ))
        action_ledger = ActionExecutionLedger(
            DeterministicPlanner((
                PlanningAction("earn", frozenset({"available"}), frozenset({"paid"})),
            )),
            (ActionExecutionPolicy("earn", duration_ticks=1),),
            events=self.events,
        )
        action_ledger.start(
            "execution-effects", "npc-a", 0, "earn",
            {"available"}, {}, plan_actions=("earn",),
        )
        completed = action_ledger.advance("execution-effects", 1, {"available"}, {})
        self.assertEqual(completed.status, "completed")

        def fail_after_households(phase, tick):
            if phase == "households":
                raise RuntimeError("untransactional household failure")
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            economic_action_adapter=economic_actions,
            household_ledger=households,
            action_execution_ledger=action_ledger,
            household_action_adapter=household_actions,
            inventory_action_adapter=inventory_actions,
            phase_observer=fail_after_households,
        )
        with self.assertRaisesRegex(RuntimeError, "untransactional household failure"):
            loop.run_tick(1, 500, self.npcs, outcome_samples={})
        self.assertEqual(economics.balance("employer"), 40.0)
        self.assertEqual(economics.balance("household"), 10.0)
        self.assertEqual(economics.balance("landlord"), 0.0)
        self.assertEqual(households.snapshot()[0].due_tick, 2)
        self.assertEqual(len(households.snapshot()), 1)
        self.assertEqual(inventory.quantity("npc-a", "meal"), 1.0)

        loop.phase_observer = None
        retried = loop.run_tick(1, 500, self.npcs, outcome_samples={})
        self.assertEqual(len(retried.economic_transfers), 1)
        self.assertEqual(len(retried.action_obligations), 1)
        self.assertEqual(len(retried.inventory_transfers), 1)
        self.assertEqual(
            tuple(item.execution_id for item in retried.action_results),
            ("execution-effects",),
        )
        self.assertEqual(len(economics.snapshot()), 1)
        self.assertEqual(len(households.snapshot()), 1)
        self.assertEqual(len(inventory.snapshot()), 1)

    def test_untransactional_phase_failure_invalidates_orchestration_cache_for_safe_retry(self):
        event = WorldEventLedger.make_event(
            "untransactional-memory", 1, "assault",
            participants=("npc-b",), witnesses=("npc-a",),
            attributes={
                "action_tag": ActionTag.CRIME_ASSAULT.value,
                "target_entity_id": "npc-b",
            },
        )
        self.events.append(event)
        def fail_after_social(phase, tick):
            if phase == "social":
                raise RuntimeError("phase failure")
        loop = PopulationExecutionLoop(
            self.loop.coordinator, self.book, self.ledger,
            phase_observer=fail_after_social,
        )
        with self.assertRaisesRegex(RuntimeError, "phase failure"):
            loop.run_tick(1, 500, self.npcs, event_ids=("untransactional-memory",), outcome_samples={"work-a": 0.2, "rest-b": 0.7})
        self.assertEqual(len(self.npcs["npc-a"].memories), 1)
        loop.phase_observer = None
        retried = loop.run_tick(
            1, 500, self.npcs, event_ids=("untransactional-memory",), outcome_samples={"work-a": 0.2, "rest-b": 0.7},
        )
        self.assertEqual(len(self.npcs["npc-a"].memories), 1)
        self.assertEqual(len(retried.social.materialized_memories), 1)

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
        household_actions = HouseholdActionAdapter(household, (
            ActionHouseholdEffect(
                "work-shift", "utility", "family", "household", "utility",
                5.0, 1, "utility obligation created by completed shift",
            ),
        ))
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            economic_action_adapter=adapter, household_ledger=household,
            household_action_adapter=household_actions,
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
        self.assertEqual(len(result.action_obligations), 1)
        self.assertEqual(result.action_obligations[0].obligation_id, "action:action-1:utility")
        self.assertEqual(economics.balance("employer"), 80.0)
        self.assertEqual(economics.balance("household"), 10.0)
        self.assertEqual(economics.balance("utility"), 10.0)

    def test_action_dispatch_and_multi_tick_execution_run_inside_population_tick(self):
        goals = GoalBook()
        goals.add(NPCGoal("goal-a", "npc-a", "work", priority=5))
        planner = DeterministicPlanner((
            PlanningAction("earn", frozenset({"available"}), frozenset({"paid"})),
        ))
        action_ledger = ActionExecutionLedger(
            planner,
            (ActionExecutionPolicy("earn", resource_costs=(("energy", 2.0),), duration_ticks=2),),
            events=self.events,
        )
        dispatch = NPCActionDispatchAdapter(action_ledger)
        facts = {"available"}
        resources = {"energy": 5.0}
        world_state = ActionWorldState({"npc-a": facts}, {"npc-a": resources})
        loop = PopulationExecutionLoop(
            self.loop.coordinator, RoutineBook(), RoutineExecutionLedger(),
            decision_cycle=NPCDecisionCycle(goals, planner),
            action_execution_ledger=action_ledger,
            action_dispatch_adapter=dispatch,
            action_world_state=world_state,
        )
        contexts = {"npc-a": NPCDecisionContext(frozenset({"available"}), {"goal-a": frozenset({"paid"})})}

        first = loop.run_tick(1, 500, self.npcs, outcome_samples={}, decision_contexts=contexts)
        self.assertEqual(first.action_dispatches[0].status, "started")
        self.assertEqual(len(action_ledger.active()), 1)
        self.assertEqual(resources["energy"], 5.0)

        second = loop.run_tick(2, 501, self.npcs, outcome_samples={}, decision_contexts=contexts)
        self.assertEqual(second.action_dispatches[0].status, "already_active")
        self.assertEqual(action_ledger.active()[0].progress_ticks, 1)

        third = loop.run_tick(3, 502, self.npcs, outcome_samples={}, decision_contexts=contexts)
        self.assertEqual(third.action_results[0].status, "completed")
        self.assertEqual(third.action_dispatches[0].status, "completed_this_tick")
        self.assertEqual(facts, {"available", "paid"})
        self.assertEqual(resources, {"energy": 3.0})
        self.assertEqual(action_ledger.active(), ())

    def test_transactional_population_loop_rejects_incomplete_participant_set(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"value": 0}
            participant = TransactionParticipant(
                "npcs", lambda: json.dumps(state),
                lambda payload: (state.clear(), state.update(json.loads(payload))),
            )
            transaction = PopulationTickTransactionCoordinator(Path(directory) / "ticks.json", (participant,))
            with self.assertRaisesRegex(ValueError, "missing participants"):
                PopulationExecutionLoop(
                    self.loop.coordinator, self.book, self.ledger,
                    transaction_coordinator=transaction,
                )

if __name__ == "__main__":
    unittest.main()
