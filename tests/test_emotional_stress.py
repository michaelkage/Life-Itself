import unittest
import json

from simreality.emotional_stress import (
    CopingProfile, NPCStressLedger, NPCStressSnapshot,
)


class EmotionalStressTests(unittest.TestCase):
    def setUp(self):
        self.profile = CopingProfile(
            "npc-a", reappraisal=0.25, distraction=0.1,
            support_seeking=0.5, suppression_cost=0.2,
            resilience=0.5, recovery_per_tick=0.02,
            exhaustion_threshold=0.6, breaking_point=0.9,
        )
        self.ledger = NPCStressLedger()

    def test_coping_strategies_reduce_stressor_differently(self):
        record = self.ledger.apply_stressor(
            record_id="stress-1", event_id="event-1", owner_id="npc-a",
            tick=1, intensity=0.8, profile=self.profile, strategy="support_seeking",
        )
        self.assertAlmostEqual(record.net_change, 0.4)
        self.assertAlmostEqual(self.ledger.stress_for("npc-a"), 0.4)

    def test_suppression_can_have_delayed_stress_cost(self):
        record = self.ledger.apply_stressor(
            record_id="stress-1", event_id="event-1", owner_id="npc-a",
            tick=0, intensity=0.5, profile=self.profile, strategy="suppression",
        )
        self.assertAlmostEqual(record.net_change, 0.6)
        self.assertAlmostEqual(record.suppression_load, 0.1)

    def test_accumulation_exhaustion_and_breaking_point_are_assessments(self):
        profile = CopingProfile("npc-a", exhaustion_threshold=0.4, breaking_point=0.8)
        for index in range(4):
            self.ledger.apply_stressor(
                record_id=f"stress-{index}", event_id=f"event-{index}",
                owner_id="npc-a", tick=0, intensity=0.2,
                profile=profile, strategy="reappraisal",
            )
        assessment = self.ledger.assess("npc-a", profile)
        self.assertTrue(assessment.at_exhaustion_threshold)
        self.assertTrue(assessment.at_breaking_point)
        self.assertEqual(assessment.exhaustion, 1.0)

    def test_recovery_is_deterministic_and_owner_specific(self):
        profile = CopingProfile("npc-a", recovery_per_tick=0.1)
        self.ledger.apply_stressor(
            record_id="stress-1", event_id="event-1", owner_id="npc-a",
            tick=0, intensity=0.6, profile=profile,
        )
        self.ledger.advance(2, {"npc-a": profile})
        self.assertAlmostEqual(self.ledger.stress_for("npc-a"), 0.4)
        self.assertEqual(self.ledger.stress_for("npc-b"), 0.0)

    def test_one_npc_advancing_does_not_consume_another_npcs_recovery_time(self):
        profile_a = CopingProfile("npc-a", recovery_per_tick=0.1)
        profile_b = CopingProfile("npc-b", recovery_per_tick=0.05)
        self.ledger.apply_stressor(record_id="stress-a", event_id="event-a", owner_id="npc-a", tick=0, intensity=0.8, profile=profile_a)
        self.ledger.apply_stressor(record_id="stress-b", event_id="event-b", owner_id="npc-b", tick=0, intensity=0.8, profile=profile_b)
        self.ledger.advance(2, {"npc-a": profile_a})
        self.assertAlmostEqual(self.ledger.stress_for("npc-a"), 0.6)
        self.assertAlmostEqual(self.ledger.stress_for("npc-b"), 0.8)
        self.ledger.advance(3, {"npc-b": profile_b})
        self.assertAlmostEqual(self.ledger.stress_for("npc-b"), 0.65)
        self.ledger.advance(3, {"npc-a": profile_a})
        self.assertAlmostEqual(self.ledger.stress_for("npc-a"), 0.5)

    def test_owner_recovery_clocks_survive_snapshot_round_trip(self):
        profile_a = CopingProfile("npc-a", recovery_per_tick=0.1)
        profile_b = CopingProfile("npc-b", recovery_per_tick=0.05)
        self.ledger.apply_stressor(record_id="stress-a", event_id="event-a", owner_id="npc-a", tick=0, intensity=0.8, profile=profile_a)
        self.ledger.apply_stressor(record_id="stress-b", event_id="event-b", owner_id="npc-b", tick=0, intensity=0.8, profile=profile_b)
        self.ledger.advance(2, {"npc-a": profile_a})
        restored = NPCStressSnapshot.capture(self.ledger).restore()
        restored.advance(3, {"npc-b": profile_b})
        self.assertAlmostEqual(restored.stress_for("npc-b"), 0.65)

    def test_legacy_v1_snapshot_restores_with_current_owner_clocks(self):
        legacy = {"version": 1, "current_tick": 4, "stress": {"npc-a": 0.5}, "records": []}
        payload = json.dumps(legacy, sort_keys=True, separators=(",", ":"))
        restored = NPCStressSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot()["version"], 2)
        self.assertEqual(restored.snapshot()["owner_ticks"], {"npc-a": 4})

    def test_replay_and_persistence(self):
        kwargs = dict(record_id="stress-1", event_id="event-1",
                      owner_id="npc-a", tick=0, intensity=0.7,
                      profile=self.profile, strategy="distraction")
        first = self.ledger.apply_stressor(**kwargs)
        self.assertEqual(self.ledger.apply_stressor(**kwargs), first)
        snapshot = NPCStressSnapshot.capture(self.ledger)
        restored = snapshot.restore()
        self.assertEqual(restored.snapshot(), self.ledger.snapshot())
        with self.assertRaises(ValueError):
            restored.apply_stressor(
                **{**kwargs, "intensity": 0.2},
            )

    def test_one_world_event_can_stress_multiple_npcs(self):
        first = CopingProfile("npc-a")
        second = CopingProfile("npc-b", reappraisal=0.5)
        self.ledger.apply_stressor(
            record_id="stress-a", event_id="shared-event", owner_id="npc-a",
            tick=0, intensity=0.6, profile=first,
        )
        self.ledger.apply_stressor(
            record_id="stress-b", event_id="shared-event", owner_id="npc-b",
            tick=0, intensity=0.6, profile=second,
        )
        self.assertAlmostEqual(self.ledger.stress_for("npc-a"), 0.6)
        self.assertAlmostEqual(self.ledger.stress_for("npc-b"), 0.3)

    def test_invalid_profile_and_future_record_rejected(self):
        with self.assertRaises(ValueError):
            CopingProfile("npc-a", exhaustion_threshold=0.9, breaking_point=0.8)
        with self.assertRaises(ValueError):
            self.ledger.apply_stressor(
                record_id="stress-1", event_id="event-1", owner_id="npc-a",
                tick=1, intensity=0.2, profile=self.profile,
            )


if __name__ == "__main__":
    unittest.main()
