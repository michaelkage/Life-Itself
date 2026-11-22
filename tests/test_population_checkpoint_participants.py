"""Concrete checkpoint participant rollback integration tests."""
import tempfile
import unittest
from pathlib import Path

from simreality.model import NPC, NPCMemory, ActionTag, Description
from simreality.population_checkpoint_participants import build_population_transaction_participants
from simreality.population_transaction import PopulationTickTransactionCoordinator
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import RoutineBook, RoutineBlock
from simreality.simulation_tick import SimulationTickCoordinator
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger, SocialInteraction
from simreality.beliefs import Evidence
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger
from simreality.household_economy import (
    EconomicAccount, EconomicLedger, EconomicTransfer, EconomicActionAdapter,
    ActionEconomicEffect, HouseholdLedger, HouseholdObligation,
)


class PopulationCheckpointParticipantTests(unittest.TestCase):
    def setUp(self):
        self.npcs = {"npc-a": NPC("npc-a"), "npc-b": NPC("npc-b")}
        self.events = WorldEventLedger()
        self.trust = SocialTrustLedger()
        self.beliefs = SocialBeliefSystem(self.trust)
        self.conversations = SocialConversationAdapter(self.trust, self.beliefs)
        self.memory = WorldEventMemoryAdapter(self.events)
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
        self.economic_actions = EconomicActionAdapter(self.economics, (
            ActionEconomicEffect("work", "employer", "family", 20, "wage"),
        ))
        self.participants = build_population_transaction_participants(
            self.npcs, self.tick, self.routines, self.routine_executions,
            economic_action_adapter=self.economic_actions,
            household_ledger=self.households,
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
                "economics", "economic_actions", "households",
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
            for failed_phase in range(6):
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
                    lambda: (
                        self.economics.transfer(EconomicTransfer(
                            f"transfer-{tick}", tick, "employer", "family", 1, "phase-test",
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
                self.assertEqual(self.households.snapshot()[0].status, "pending")

if __name__ == "__main__":
    unittest.main()
