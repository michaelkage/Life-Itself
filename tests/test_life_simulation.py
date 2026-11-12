"""Regression coverage for daily life, support, estate resolution, and ghost decisions."""
import unittest
from random import Random

from simreality.campaign import LifeItselfCampaign
from simreality.health_life import CharacterHealth, HealthCondition, SocialObligation
from simreality.life_simulation import (
    GhostWindow, LifeSimulation, PersonProfile, ResponsibilityOutcome, Treatment,
)


class LifeSimulationTests(unittest.TestCase):
    def test_treatment_and_uncertain_recovery_affect_work_and_income(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("patient")
        world = campaign.active_world
        world.money["patient"] = 50
        world.health["patient"].conditions.append(HealthCondition(
            "injury", "injury", 0.9, recovery_per_day=0.1,
            activity_limits={"work": 0.1}))
        sim = LifeSimulation(world, seed=7)
        sim.register_person(PersonProfile("patient"))
        estimate = sim.estimate_recovery("patient", "injury")
        self.assertLess(estimate.lower_bound, estimate.upper_bound)
        self.assertTrue(sim.prescribe_treatment("patient", Treatment(
            "care", "injury", effectiveness=0.5, daily_cost=5, care_hours=2)))
        record = sim.simulate_day(wages={"patient": 100})[0]
        self.assertEqual(record.wage_earned, 0)
        self.assertEqual(record.wage_lost, 100)
        self.assertEqual(world.money["patient"], 45)
        self.assertGreater(record.care_hours_needed, 0)

    def test_daily_recovery_and_condition_duration_advance_exactly_once(self):
        world = LifeItselfCampaign().active_world
        world.health["patient"] = CharacterHealth("patient")
        condition = HealthCondition("injury", "injury", 0.8, recovery_per_day=0.2)
        world.health["patient"].conditions.append(condition)
        sim = LifeSimulation(world, seed=1)

        lower, upper = 0.08, 0.32
        sampled_recovery = Random(1).uniform(lower, upper)
        sim.simulate_day()

        self.assertAlmostEqual(condition.severity, 0.8 - sampled_recovery)
        self.assertEqual(condition.days_present, 1)
        self.assertEqual(world.day, 1)

    def test_treatment_rejects_invalid_economic_and_clinical_inputs(self):
        for kwargs in (
            {"effectiveness": 0.5, "daily_cost": -1.0},
            {"effectiveness": 1.1, "daily_cost": 1.0},
            {"effectiveness": 0.5, "daily_cost": 1.0, "care_hours": -2.0},
            {"effectiveness": 0.5, "daily_cost": 1.0, "complication_risk": 1.1},
            {"effectiveness": float("nan"), "daily_cost": 1.0},
        ):
            values = {"effectiveness": 0.5, "daily_cost": 1.0, **kwargs}
            with self.assertRaises(ValueError):
                Treatment("invalid", "injury", **values)

    def test_duplicate_treatment_id_cannot_charge_twice(self):
        world = LifeItselfCampaign().active_world
        world.money["patient"] = 20.0
        world.health["patient"] = CharacterHealth("patient", [
            HealthCondition("injury", "injury", 0.8, recovery_per_day=0.1),
        ])
        sim = LifeSimulation(world)
        treatment = Treatment("care", "injury", 0.5, 5.0)
        self.assertTrue(sim.prescribe_treatment("patient", treatment))
        with self.assertRaisesRegex(ValueError, "duplicate treatment ID"):
            sim.prescribe_treatment("patient", Treatment("care", "injury", 0.5, 5.0))
        sim.simulate_day()
        self.assertEqual(world.money["patient"], 15.0)

    def test_reciprocal_support_transfers_money_and_builds_trust(self):
        world = LifeItselfCampaign().active_world
        world.money.update({"helper": 40, "recipient": 0})
        sim = LifeSimulation(world)
        sim.register_person(PersonProfile("helper"))
        sim.register_person(PersonProfile("recipient"))
        self.assertTrue(sim.provide_support("helper", "recipient", money=15, care_hours=3))
        self.assertEqual(world.money["helper"], 25)
        self.assertEqual(world.money["recipient"], 15)
        self.assertGreater(world.trust["helper->recipient"], 0)
        self.assertGreater(world.trust["recipient->helper"], 0)

    def test_death_resolves_debt_from_estate_before_unresolved(self):
        world = LifeItselfCampaign().active_world
        world.money.update({"deceased": 20, "creditor": 0})
        sim = LifeSimulation(world, seed=2)
        sim.register_person(PersonProfile("deceased"))
        sim.create_responsibility(SocialObligation(
            "debt", "deceased", "creditor", money_due=15, due_day=99))
        results = sim.resolve_after_death("deceased")
        self.assertEqual(results[0].outcome, ResponsibilityOutcome.PAID_FROM_ESTATE)
        self.assertEqual(world.money["creditor"], 15)

    def test_death_obligation_resolution_is_idempotent(self):
        world = LifeItselfCampaign().active_world
        world.money.update({"deceased": 0.0, "helper": 20.0, "creditor": 0.0})
        sim = LifeSimulation(world)
        sim.register_person(PersonProfile("deceased"))
        sim.register_person(PersonProfile(
            "helper", personality={"compassion": 1.0, "duty": 1.0},
            relationships={"deceased": 1.0},
        ))
        sim.create_responsibility(SocialObligation(
            "debt-once", "deceased", "creditor", money_due=15.0, due_day=99,
        ))

        first = sim.resolve_after_death("deceased")
        money_after_first = dict(world.money)
        trust_after_first = dict(world.trust)
        second = sim.resolve_after_death("deceased")

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(world.money, money_after_first)
        self.assertEqual(world.trust, trust_after_first)
        self.assertEqual(world.money["helper"], 5.0)
        self.assertEqual(world.money["creditor"], 15.0)

    def test_ghost_window_uses_npc_personality_memory_and_relationship(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("lost")
        campaign.record_death("illness")
        campaign.continue_as_ghost()
        sim = LifeSimulation(campaign.active_world, seed=4)
        sim.register_person(PersonProfile("npc", personality={
            "spiritual_openness": 1, "fearfulness": 1, "stubbornness": 0,
        }, memories={"lost": 1}, relationships={"lost": 1}))
        sim.schedule_ghost_window(GhostWindow(2, 4, permitted_actions=("sound",)))
        outside = sim.attempt_ghost_influence("npc", "sound", 1)
        inside = sim.attempt_ghost_influence("npc", "sound", 3)
        self.assertFalse(outside.accepted)
        self.assertIn("outside", outside.reason)
        self.assertTrue(inside.accepted)
        self.assertGreater(inside.influence_score, 0.9)


if __name__ == "__main__":
    unittest.main()
