import unittest

from simreality import (
    ActionTag, NPC, CopingProfile, NPCStressLedger,
    SimulationTickCoordinator, SimulationWorldCheckpoint,
    SocialBeliefSystem, SocialConversationAdapter, SocialTrustLedger,
    WorldEventLedger, WorldEventMemoryAdapter,
    ConditioningProfile, NPCConditioningLedger,
)


class NPCStressCheckpointTests(unittest.TestCase):
    def make_world(self):
        events = WorldEventLedger((WorldEventLedger.make_event(
            "stress-event", 2, "incident", participants=("npc-a",),
            attributes={"action_tag": ActionTag.CRIME_THEFT.value},
        ),))
        npcs = {"npc-a": NPC("npc-a")}
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        memory = WorldEventMemoryAdapter(events)
        conversations = SocialConversationAdapter(trust, beliefs)
        coordinator = SimulationTickCoordinator(events, memory, conversations)
        return coordinator, npcs

    def test_stress_round_trip_and_backward_compatible_optional_section(self):
        coordinator, npcs = self.make_world()
        stress = NPCStressLedger()
        stress.apply_stressor(
            record_id="record-1", event_id="stress-event", owner_id="npc-a",
            tick=2, intensity=0.8, profile=CopingProfile("npc-a"),
        )
        payload = SimulationWorldCheckpoint.capture(
            3, coordinator, npcs, stress=stress,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertAlmostEqual(restored.stress.stress_for("npc-a"), 0.8)
        self.assertEqual(len(restored.stress.records()), 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                3, restored.coordinator, restored.npcs, stress=restored.stress,
            ).to_json(), payload,
        )
        old_payload = SimulationWorldCheckpoint.capture(3, coordinator, npcs).to_json()
        self.assertIsNone(SimulationWorldCheckpoint.from_json(old_payload).restore().stress)

    def test_checkpoint_rejects_stress_for_unknown_npc(self):
        coordinator, npcs = self.make_world()
        stress = NPCStressLedger(initial_stress={"missing": 0.2})
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(3, coordinator, npcs, stress=stress)

    def test_checkpoint_rejects_stress_without_authoritative_source_event(self):
        coordinator, npcs = self.make_world()
        stress = NPCStressLedger()
        stress.apply_stressor(
            record_id="record-1", event_id="unlogged", owner_id="npc-a",
            tick=2, intensity=0.8, profile=CopingProfile("npc-a"),
        )
        with self.assertRaisesRegex(ValueError, "missing world event"):
            SimulationWorldCheckpoint.capture(3, coordinator, npcs, stress=stress)

    def test_checkpoint_rejects_future_stress_tick(self):
        coordinator, npcs = self.make_world()
        stress = NPCStressLedger()
        stress.apply_stressor(
            record_id="record-1", event_id="stress-event", owner_id="npc-a",
            tick=2, intensity=0.8, profile=CopingProfile("npc-a"),
        )
        with self.assertRaisesRegex(ValueError, "after the checkpoint tick"):
            SimulationWorldCheckpoint.capture(1, coordinator, npcs, stress=stress)

    def test_conditioning_round_trip_and_optional_section(self):
        coordinator, npcs = self.make_world()
        conditioning = NPCConditioningLedger()
        conditioning.learn(
            record_id="condition-1", source_event_id="stress-event",
            owner_id="npc-a", cue="raised_voice", tick=2, outcome=-1.0,
            intensity=0.8, profile=ConditioningProfile("npc-a"),
        )
        payload = SimulationWorldCheckpoint.capture(
            3, coordinator, npcs, conditioning=conditioning,
        ).to_json()
        restored = SimulationWorldCheckpoint.from_json(payload).restore()
        self.assertLess(restored.conditioning.association_for("npc-a", "raised_voice"), 0)
        self.assertEqual(len(restored.conditioning.records()), 1)
        self.assertEqual(
            SimulationWorldCheckpoint.capture(
                3, restored.coordinator, restored.npcs,
                conditioning=restored.conditioning,
            ).to_json(), payload,
        )
        legacy = SimulationWorldCheckpoint.capture(3, coordinator, npcs).to_json()
        self.assertIsNone(SimulationWorldCheckpoint.from_json(legacy).restore().conditioning)

    def test_checkpoint_rejects_conditioning_without_source_event(self):
        coordinator, npcs = self.make_world()
        conditioning = NPCConditioningLedger()
        conditioning.learn(
            record_id="condition-1", source_event_id="missing",
            owner_id="npc-a", cue="raised_voice", tick=2, outcome=-1.0,
            intensity=1.0, profile=ConditioningProfile("npc-a"),
        )
        with self.assertRaisesRegex(ValueError, "missing world event"):
            SimulationWorldCheckpoint.capture(3, coordinator, npcs, conditioning=conditioning)

    def test_checkpoint_rejects_conditioning_for_unknown_npc(self):
        coordinator, npcs = self.make_world()
        conditioning = NPCConditioningLedger(associations={("missing", "cue"): -0.5})
        with self.assertRaisesRegex(ValueError, "missing from checkpoint"):
            SimulationWorldCheckpoint.capture(3, coordinator, npcs, conditioning=conditioning)


if __name__ == "__main__":
    unittest.main()
