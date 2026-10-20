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


if __name__ == "__main__":
    unittest.main()
