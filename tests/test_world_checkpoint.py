import json
import unittest

from simreality import (
    ActionTag, NPC, ConversationIntent, SocialBeliefSystem,
    ObservedClaim, SocialConsequenceRecorder, SocialConversationAdapter, SocialTrustLedger, SimulationTickCoordinator,
    SimulationWorldCheckpoint, WitnessedSocialEvent, WorldEventLedger, WorldEventMemoryAdapter,
    LifeItselfCampaign, LifeState,
)


class SimulationWorldCheckpointTests(unittest.TestCase):
    def make_simulation(self):
        events = WorldEventLedger((
            WorldEventLedger.make_event(
                "event-1", 3, "incident",
                participants=("speaker", "subject"), witnesses=("speaker",),
                attributes={
                    "action_tag": ActionTag.CRIME_THEFT.value,
                    "target_entity_id": "subject",
                    "memory_impact": 0.9,
                },
            ),
        ))
        npcs = {"speaker": NPC("speaker"), "listener": NPC("listener")}
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        memory = WorldEventMemoryAdapter(events, ticks_per_hour=2.0)
        conversations = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        consequences = SocialConsequenceRecorder(trust, beliefs)
        consequences.record(WitnessedSocialEvent(
            "event-social-1", "listener", "speaker", 3, -1, 0.4,
            (ObservedClaim("claim-1", 1, 0.7),),
        ))
        intent = ConversationIntent("chat-3", "listener", "speaker")
        coordinator.step(3, npcs, event_ids=("event-1",), conversations=(intent,))
        return coordinator, npcs, consequences

    def test_round_trip_restores_dependencies_and_idempotent_tick_replay(self):
        coordinator, npcs, consequences = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},
            consequence_recorder=consequences,
        ).to_json()

        restored_checkpoint = SimulationWorldCheckpoint.from_json(payload)
        restored = restored_checkpoint.restore()
        self.assertEqual(restored.current_tick, 4)
        self.assertEqual(restored.metadata, (("seed", 42), ("world", "alpha")))
        self.assertEqual(restored.memory_adapter.ticks_per_hour, 2.0)
        self.assertIsNotNone(restored.consequence_recorder)
        before_consequence_trust = restored.trust.snapshot()
        replayed_consequence = restored.consequence_recorder.record(WitnessedSocialEvent(
            "event-social-1", "listener", "speaker", 3, -1, 0.4,
            (ObservedClaim("claim-1", 1, 0.7),),
        ))
        self.assertEqual(replayed_consequence.event_id, "event-social-1")
        self.assertEqual(restored.trust.snapshot(), before_consequence_trust)

        before = list(restored.npcs["speaker"].memories)
        result = restored.coordinator.step(
            3, restored.npcs, event_ids=("event-1",),
            conversations=(ConversationIntent("chat-3", "listener", "speaker"),),
        )
        self.assertEqual(restored.npcs["speaker"].memories, before)
        self.assertEqual(len(restored.npcs["speaker"].memories), 1)
        self.assertEqual(result.tick, 3)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                4, restored.coordinator, restored.npcs,
                metadata=dict(restored.metadata),
                consequence_recorder=restored.consequence_recorder,
            ).to_json(),
            payload,
        )

    def test_consequence_section_is_optional(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn("consequence_replay", payload)
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNone(restored.consequence_recorder)

    def test_consequence_recorder_must_share_checkpoint_ledgers(self):
        coordinator, npcs, _ = self.make_simulation()
        unrelated_trust = SocialTrustLedger()
        unrelated_beliefs = SocialBeliefSystem(unrelated_trust)
        unrelated_recorder = SocialConsequenceRecorder(unrelated_trust, unrelated_beliefs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, consequence_recorder=unrelated_recorder,
            )

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json('{"schema_version":99}')

    def test_invalid_clock_or_metadata_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(-1, coordinator, npcs)
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.capture(
                4, coordinator, npcs, metadata={"not-finite": float("nan")},
            )


    def test_checkpoint_rejects_event_replay_reference_to_missing_event(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["tick_replay"]["entries"][0]["event_ids"] = ["missing-event"]
        checkpoint = SimulationWorldCheckpoint.from_json(json.dumps(payload))
        with self.assertRaises((ValueError, KeyError)):
            checkpoint.restore()

    def test_checkpoint_rejects_clock_that_disagrees_with_event_envelope(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["events"]["current_tick"] = 5
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json(json.dumps(payload))

    def test_checkpoint_rejects_memory_replay_for_non_witness(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = json.loads(SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json())
        payload["memory_replay"]["entries"][0]["witness_id"] = "listener"
        checkpoint = SimulationWorldCheckpoint.from_json(json.dumps(payload))
        with self.assertRaises(ValueError):
            checkpoint.restore()

    def test_checkpoint_json_is_canonical_after_whitespace_and_key_reordering(self):
        coordinator, npcs, consequences = self.make_simulation()
        checkpoint = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, metadata={"world": "alpha", "seed": 42},
            consequence_recorder=consequences,
        )
        parsed = json.loads(checkpoint.to_json())
        reformatted = json.dumps(parsed, indent=2, sort_keys=False)
        self.assertEqual(
            SimulationWorldCheckpoint.from_json(reformatted).to_json(),
            checkpoint.to_json(),
        )


    def test_campaign_lifecycle_round_trips_inside_world_checkpoint(self):
        coordinator, npcs, _ = self.make_simulation()
        campaign = LifeItselfCampaign()
        campaign.begin_first_life("first-life")
        campaign.active_world.money["first-life"] = 75.0
        campaign.record_death("illness")
        campaign.continue_as_ghost()
        payload = SimulationWorldCheckpoint.capture(
            4, coordinator, npcs, campaign=campaign,
        ).to_json()

        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertIsNotNone(restored.campaign)
        self.assertEqual(restored.campaign.active_world.life.state, LifeState.GHOST)
        self.assertEqual(restored.campaign.active_world.life.death_cause, "illness")
        self.assertEqual(restored.campaign.active_world.money["first-life"], 75.0)

        restored.campaign.start_fresh_world("second-life")
        self.assertEqual(restored.campaign.active_world.life.character_id, "second-life")
        self.assertEqual(len(restored.campaign.archived_worlds), 1)
        self.assertEqual(
            restored.campaign.visit_archive(restored.campaign.archived_worlds[0].archive_id)
            .money["first-life"],
            75.0,
        )

    def test_campaign_section_is_optional_and_invalid_campaign_is_rejected(self):
        coordinator, npcs, _ = self.make_simulation()
        payload = SimulationWorldCheckpoint.capture(4, coordinator, npcs).to_json()
        self.assertNotIn('"campaign"', payload)
        altered = json.loads(payload)
        altered["campaign"] = {"schema_version": 99}
        with self.assertRaises(ValueError):
            SimulationWorldCheckpoint.from_json(json.dumps(altered))


if __name__ == "__main__":
    unittest.main()
