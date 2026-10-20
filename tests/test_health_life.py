"""Regression tests for persistent health, obligations, finite lives, and save/load."""
import unittest

from simreality.health_life import (
    CampaignLife, CharacterHealth, HealthCondition, LifeState,
    PersistentWorld, SocialObligation,
)


class HealthLifeTests(unittest.TestCase):
    def test_health_recovers_gradually_and_limits_activity(self):
        health = CharacterHealth("c1", [HealthCondition(
            "sprain", "injury", 0.8, recovery_per_day=0.2,
            activity_limits={"run": 0.25},
        )])
        self.assertAlmostEqual(health.activity_capacity("run"), 0.4)
        health.advance_day()
        self.assertAlmostEqual(health.conditions[0].severity, 0.6)
        self.assertAlmostEqual(health.activity_capacity("run"), 0.55)

    def test_obligation_settlement_updates_money_stress_and_trust_once(self):
        world = PersistentWorld(money={"a": 100}, stress={"a": 0})
        world.add_obligation(SocialObligation("o1", "a", "b", 40, 0.2, 0.1, due_day=3))
        self.assertTrue(world.settle_obligation("o1"))
        self.assertFalse(world.settle_obligation("o1"))
        self.assertEqual(world.money["a"], 60)
        self.assertAlmostEqual(world.stress["a"], 0.2)
        self.assertAlmostEqual(world.trust["a->b"], 0.1)

    def test_missed_obligation_changes_stress_and_trust(self):
        world = PersistentWorld(stress={"a": 0}, trust={"a->b": 0.5})
        world.add_obligation(SocialObligation("o1", "a", "b", due_day=0, stress_delta=0.3))
        world.advance_day()
        self.assertTrue(world.obligations[0].missed)
        self.assertGreater(world.stress["a"], 0)
        self.assertAlmostEqual(world.trust["a->b"], 0.35)

    def test_death_spectator_ghost_and_new_life_preserve_archive(self):
        world = PersistentWorld(day=5, money={"first": 25}, life=CampaignLife("first", started_day=0))
        archive = world.kill_current_life("injury")
        self.assertEqual(world.life.state, LifeState.SPECTATOR)
        world.enter_ghost_state()
        self.assertFalse(world.ghost_influence(allowed_window=False))
        self.assertTrue(world.ghost_influence(allowed_window=True, cooldown_days=7))
        self.assertFalse(world.ghost_influence(allowed_window=True, cooldown_days=7))
        world.start_new_life("second")
        self.assertEqual(len(world.archives), 1)
        self.assertEqual(world.archives[0].archive_id, archive.archive_id)
        self.assertEqual(world.archives[0].world_state["money"]["first"], 25)
        self.assertEqual(world.life.character_id, "second")
        self.assertEqual(world.life.state, LifeState.ACTIVE)

    def test_save_load_continues_multiple_day_state(self):
        world = PersistentWorld(day=2, money={"a": 12}, life=CampaignLife("a"))
        world.health["a"] = CharacterHealth("a", [
            HealthCondition("bruise", "injury", 0.5, recovery_per_day=0.1)
        ])
        world.add_obligation(SocialObligation("o", "a", "b", money_due=5, due_day=4))
        restored = PersistentWorld.from_json(world.to_json())
        restored.advance_day()
        restored.advance_day()
        self.assertEqual(restored.day, 4)
        self.assertAlmostEqual(restored.health["a"].conditions[0].severity, 0.3)
        self.assertFalse(restored.obligations[0].missed)


if __name__ == "__main__":
    unittest.main()
