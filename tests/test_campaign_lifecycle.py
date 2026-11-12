"""Campaign-level regression tests for world archives and new-life isolation."""
import unittest

from simreality.campaign import LifeItselfCampaign
from simreality.health_life import CharacterHealth, HealthCondition, LifeState


class CampaignTests(unittest.TestCase):
    def test_new_life_starts_separate_world_and_old_world_is_visitable(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("old-character")
        old = campaign.active_world
        old.day = 12
        old.money["old-character"] = 77
        old.world_flags["town_changed"] = True
        campaign.record_death("illness")
        campaign.continue_as_ghost()

        archive_id = old.archives[-1].archive_id
        campaign.start_fresh_world("new-character", label="First timeline")
        self.assertEqual(campaign.active_world.day, 0)
        self.assertEqual(campaign.active_world.life.character_id, "new-character")
        self.assertEqual(campaign.active_world.life.state, LifeState.ACTIVE)
        self.assertNotIn("old-character", campaign.active_world.money)

        visited = campaign.visit_archive(archive_id)
        self.assertEqual(visited.day, 12)
        self.assertEqual(visited.money["old-character"], 77)
        visited.money["old-character"] = 0
        self.assertEqual(campaign.visit_archive(archive_id).money["old-character"], 77)

    def test_cannot_start_fresh_world_before_death(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("alive")
        with self.assertRaises(RuntimeError):
            campaign.start_fresh_world("other")

    def test_campaign_save_load_preserves_archives_and_active_world(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first")
        campaign.active_world.money["first"] = 22
        campaign.record_death("accident")
        archive_id = campaign.active_world.archives[-1].archive_id
        campaign.start_fresh_world("second")
        campaign.active_world.money["second"] = 8

        loaded = LifeItselfCampaign.from_json(campaign.to_json())
        self.assertEqual(loaded.active_world.money["second"], 8)
        self.assertEqual(len(loaded.archived_worlds), 1)
        self.assertEqual(loaded.visit_archive(archive_id).money["first"], 22)

    def test_health_and_obligations_continue_after_save_load(self):
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("person")
        world = campaign.active_world
        world.health["person"] = CharacterHealth("person", [
            HealthCondition("injury", "wound", 0.7, recovery_per_day=0.1)
        ])
        world.advance_day()
        loaded = LifeItselfCampaign.from_json(campaign.to_json())
        loaded.advance_day()
        condition = loaded.active_world.health["person"].conditions[0]
        self.assertAlmostEqual(condition.severity, 0.5)



    def test_life_simulation_state_follows_archived_timeline_and_restores_detached(self):
        from simreality.health_life import SocialObligation
        from simreality.life_simulation import (
            GhostWindow, LifeSimulation, PersonProfile, Treatment,
        )

        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first")
        world = campaign.active_world
        world.money["first"] = 12.0
        world.add_obligation(SocialObligation(
            "estate-debt", "first", "creditor", money_due=5.0, due_day=10,
        ))
        simulation = LifeSimulation(world, seed=41)
        simulation.register_person(PersonProfile(
            "first", personality={"compassion": 0.8},
            memories={"turning-point": 0.7}, relationships={"creditor": 0.9},
        ))
        simulation.schedule_ghost_window(GhostWindow(
            0, 24, 1.0, ("comfort",),
        ))
        campaign.record_death("illness", life_simulation=simulation)
        self.assertEqual(len(simulation.resolutions), 1)
        self.assertEqual(world.money["creditor"], 5.0)
        campaign.continue_as_ghost(life_simulation=simulation)
        simulation.attempt_ghost_influence("first", "comfort", 12.0)

        archive_id = world.archives[-1].archive_id
        fresh_simulation = campaign.start_fresh_life(
            "second", simulation, seed=99, label="First life",
        )
        self.assertIs(fresh_simulation.world, campaign.active_world)
        self.assertEqual(fresh_simulation.people, {})
        self.assertEqual(len(campaign.archived_life_simulations), 1)

        archived_world, archived_simulation = campaign.visit_archive_runtime(archive_id)
        self.assertIsNotNone(archived_simulation)
        self.assertIs(archived_simulation.world, archived_world)
        self.assertEqual(
            archived_simulation.people["first"].memories["turning-point"], 0.7,
        )
        self.assertEqual(len(archived_simulation.resolutions), 1)
        self.assertEqual(len(archived_simulation.ghost_action_log), 1)
        self.assertEqual(archived_world.money["creditor"], 5.0)

        archived_simulation.people["first"].memories["turning-point"] = -1.0
        _, pristine_simulation = campaign.visit_archive_runtime(archive_id)
        self.assertEqual(
            pristine_simulation.people["first"].memories["turning-point"], 0.7,
        )

        loaded = LifeItselfCampaign.from_json(campaign.to_json())
        loaded_world, loaded_simulation = loaded.visit_archive_runtime(archive_id)
        self.assertEqual(loaded_world.money["creditor"], 5.0)
        self.assertEqual(
            loaded_simulation.people["first"].memories["turning-point"], 0.7,
        )
        self.assertEqual(
            loaded_simulation.random.random(), pristine_simulation.random.random(),
        )

    def test_campaign_rejects_life_simulation_bound_to_another_timeline(self):
        from simreality.life_simulation import LifeSimulation

        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first")
        other_campaign = LifeItselfCampaign()
        other_campaign.begin_first_life("other")
        simulation = LifeSimulation(other_campaign.active_world)
        with self.assertRaisesRegex(ValueError, "share the campaign timeline"):
            campaign.record_death("illness", life_simulation=simulation)
        self.assertEqual(campaign.active_world.life.state, LifeState.ACTIVE)

    def test_campaign_loads_legacy_payload_without_archived_service_states(self):
        import json

        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first")
        campaign.record_death("accident")
        campaign.start_fresh_world("second")
        payload = json.loads(campaign.to_json())
        payload.pop("archived_life_simulations", None)
        loaded = LifeItselfCampaign.from_json(json.dumps(payload))
        self.assertEqual(loaded.archived_life_simulations, {})
        archive_id = loaded.archived_worlds[0].archive_id
        world, simulation = loaded.visit_archive_runtime(archive_id)
        self.assertEqual(world.life.character_id, "first")
        self.assertIsNone(simulation)

    def test_campaign_rejects_archived_service_state_for_unknown_timeline(self):
        import json

        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first")
        payload = json.loads(campaign.to_json())
        payload["archived_life_simulations"] = {"missing-timeline": "{}"}
        with self.assertRaisesRegex(ValueError, "known timeline IDs"):
            LifeItselfCampaign.from_json(json.dumps(payload))

if __name__ == "__main__":
    unittest.main()
