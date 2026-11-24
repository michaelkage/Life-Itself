import unittest

from simreality.population_budget import PopulationBudgetController
from simreality.population_lod_policy import PopulationLODPolicy, SubsystemLODPolicy
from simreality.population_spatial import PopulationLOD, PopulationSpatialScheduler
from simreality.presence import NPCPresence, PresenceLedger


class PopulationBudgetControllerTests(unittest.TestCase):
    def setUp(self):
        self.policy = PopulationLODPolicy({
            PopulationLOD.FULL: (SubsystemLODPolicy("full", 1),),
            PopulationLOD.STANDARD: (SubsystemLODPolicy("standard", 1),),
            PopulationLOD.BACKGROUND: (SubsystemLODPolicy("background", 1),),
            PopulationLOD.DORMANT: (),
        })
        self.controller = PopulationBudgetController(
            10.0, utilization_target=1.0, ewma_alpha=0.25,
            default_subsystem_cost_ms=1.0,
        )
        self.controller.record_phase_sample("full", 8.0, 4)
        self.controller.record_phase_sample("standard", 4.0, 4)
        self.controller.record_phase_sample("background", 2.0, 4)

    def test_allocation_obeys_tick_budget_and_roster_ceiling(self):
        allocation = self.controller.allocate(
            4,
            {
                PopulationLOD.FULL: 15,
                PopulationLOD.STANDARD: 15,
                PopulationLOD.BACKGROUND: 15,
                PopulationLOD.DORMANT: 0,
            },
            self.policy,
            max_total_owners=15,
        )
        self.assertLessEqual(allocation.estimated_tick_ms, 10.0 + 1e-9)
        self.assertLessEqual(
            allocation.full_budget + allocation.standard_budget + allocation.background_budget,
            15,
        )
        self.assertGreater(allocation.full_budget, 0)
        self.assertGreater(allocation.standard_budget, 0)
        self.assertGreater(allocation.background_budget, 0)
        self.assertEqual(
            dict(allocation.tier_costs_ms),
            {
                PopulationLOD.FULL: 2.0,
                PopulationLOD.STANDARD: 1.0,
                PopulationLOD.BACKGROUND: 0.5,
            },
        )

    def test_ewma_uses_per_owner_cost_and_snapshot_round_trips(self):
        self.controller.record_phase_sample("full", 16.0, 4)
        self.assertAlmostEqual(self.controller.subsystem_cost_ms("full"), 2.5)
        restored = PopulationBudgetController.from_json(self.controller.to_json())
        self.assertEqual(restored.to_json(), self.controller.to_json())
        self.assertAlmostEqual(restored.subsystem_cost_ms("full"), 2.5)

    def test_restore_json_preserves_controller_identity_and_replaces_measurements(self):
        reference = self.controller
        other = PopulationBudgetController(5.0, utilization_target=0.5)
        other.record_phase_sample("social", 6.0, 2)
        self.controller.restore_json(other.to_json())
        self.assertIs(reference, self.controller)
        self.assertEqual(self.controller.target_tick_ms, 5.0)
        self.assertEqual(self.controller.subsystem_cost_ms("social"), 3.0)
        self.assertEqual(self.controller.to_json(), other.to_json())

    def test_empty_phase_sample_does_not_change_cost_estimate(self):
        before = self.controller.subsystem_cost_ms("full")
        self.controller.record_phase_sample("full", 100.0, 0)
        self.assertEqual(self.controller.subsystem_cost_ms("full"), before)

    def test_invalid_samples_and_budget_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            self.controller.record_phase_sample("full", -1.0, 2)
        with self.assertRaises(ValueError):
            self.controller.record_phase_sample("full", 1.0, -1)
        with self.assertRaises(ValueError):
            self.controller.allocate(
                1,
                {tier: 1 for tier in PopulationLOD},
                self.policy,
                max_total_owners=5,
            )

    def test_tiers_with_no_due_subsystems_receive_no_owner_budget(self):
        policy = PopulationLODPolicy({
            PopulationLOD.FULL: (SubsystemLODPolicy("disabled", 1, False),),
            PopulationLOD.STANDARD: (SubsystemLODPolicy("standard", 1),),
            PopulationLOD.BACKGROUND: (),
            PopulationLOD.DORMANT: (),
        })
        allocation = self.controller.allocate(
            1,
            {
                PopulationLOD.FULL: 10,
                PopulationLOD.STANDARD: 10,
                PopulationLOD.BACKGROUND: 10,
                PopulationLOD.DORMANT: 0,
            },
            policy,
            max_total_owners=10,
        )
        self.assertEqual(allocation.full_budget, 0)
        self.assertGreater(allocation.standard_budget, 0)
        self.assertEqual(allocation.background_budget, 0)

    def test_empty_tier_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            PopulationBudgetController(10.0, tier_weights={})

    def test_adaptive_spatial_schedule_uses_measured_budget(self):
        presence = PresenceLedger(tuple(
            NPCPresence(owner, "at_location", "district-a", None, None, 0.0, 0)
            for owner in ("npc-a", "npc-b", "npc-c", "npc-d", "npc-e")
        ))
        scheduler = PopulationSpatialScheduler(presence)
        schedule, allocation = scheduler.schedule_adaptive(
            2,
            ("npc-a", "npc-b", "npc-c", "npc-d", "npc-e"),
            {
                "npc-a": 1.0, "npc-b": 0.8, "npc-c": 0.6,
                "npc-d": 0.4, "npc-e": 0.2,
            },
            budget_controller=self.controller,
            lod_policy=self.policy,
        )
        self.assertEqual(len(schedule.selected_owner_ids), 5)
        self.assertEqual(len(schedule.deferred_owner_ids), 0)
        self.assertLessEqual(
            allocation.full_budget + allocation.standard_budget + allocation.background_budget,
            5,
        )
        replay, replay_allocation = scheduler.schedule_adaptive(
            2,
            ("npc-a", "npc-b", "npc-c", "npc-d", "npc-e"),
            {
                "npc-a": 1.0, "npc-b": 0.8, "npc-c": 0.6,
                "npc-d": 0.4, "npc-e": 0.2,
            },
            budget_controller=self.controller,
            lod_policy=self.policy,
        )
        self.assertIs(replay, schedule)
        self.assertEqual(replay_allocation, allocation)


if __name__ == "__main__":
    unittest.main()
