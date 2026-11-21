import unittest

from simreality.population_lod_policy import (
    PopulationLODPolicy, SubsystemLODPolicy, default_population_lod_policy,
)
from simreality.population_spatial import PopulationLOD


class PopulationLODPolicyTests(unittest.TestCase):
    def test_default_policy_resolves_subsystem_specific_cadence(self):
        policy = default_population_lod_policy()
        self.assertEqual(policy.due_subsystems(PopulationLOD.FULL, 3),
                         ("decision", "economy", "memory", "routine", "social", "travel"))
        self.assertEqual(policy.due_subsystems(PopulationLOD.STANDARD, 2),
                         ("decision", "economy", "memory", "routine", "social", "travel"))
        self.assertEqual(policy.due_subsystems(PopulationLOD.BACKGROUND, 2),
                         ("routine", "travel"))
        self.assertEqual(policy.due_subsystems(PopulationLOD.DORMANT, 3), ("travel",))

    def test_custom_policy_can_disable_individual_subsystems(self):
        from simreality.population_spatial import PopulationLOD
        tiers = {
            tier: (SubsystemLODPolicy("travel", 1),)
            for tier in PopulationLOD
        }
        tiers[PopulationLOD.FULL] = (
            SubsystemLODPolicy("travel", 1),
            SubsystemLODPolicy("economy", 3, False),
        )
        policy = PopulationLODPolicy(tiers)
        self.assertEqual(policy.due_subsystems(PopulationLOD.FULL, 3), ("travel",))
        self.assertIsNotNone(policy.policy_for(PopulationLOD.FULL, "economy"))

    def test_all_lod_tiers_must_be_defined(self):
        with self.assertRaisesRegex(ValueError, "every PopulationLOD"):
            PopulationLODPolicy({PopulationLOD.FULL: ()})


if __name__ == "__main__":
    unittest.main()
