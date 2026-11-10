import unittest

from simreality import ConditioningProfile, NPCConditioningLedger, NPCConditioningSnapshot


class NPCConditioningTests(unittest.TestCase):
    def test_reinforcement_builds_owner_specific_cue_association(self):
        ledger = NPCConditioningLedger()
        profile = ConditioningProfile("npc", learning_rate=0.5)
        ledger.learn(record_id="r1", source_event_id="e1", owner_id="npc",
                     cue="raised_voice", tick=1, outcome=-1, intensity=1,
                     profile=profile)
        self.assertEqual(ledger.assess("npc", "raised_voice").direction, "avoid")
        self.assertEqual(ledger.association_for("other", "raised_voice"), 0)

    def test_repeated_reinforcement_strengthens_association(self):
        ledger = NPCConditioningLedger()
        profile = ConditioningProfile("npc", learning_rate=0.5)
        for i in range(2):
            ledger.learn(record_id=f"r{i}", source_event_id=f"e{i}", owner_id="npc",
                         cue="support", tick=i, outcome=1, intensity=1, profile=profile)
        self.assertAlmostEqual(ledger.association_for("npc", "support"), 0.75)

    def test_extinction_weakens_without_reversing_association(self):
        ledger = NPCConditioningLedger(associations={("npc", "door_slam"): -0.8})
        profile = ConditioningProfile("npc", extinction_rate=0.25)
        ledger.learn(record_id="r", source_event_id="e", owner_id="npc",
                     cue="door_slam", tick=1, outcome=1, intensity=1,
                     profile=profile, mode="extinguish")
        self.assertAlmostEqual(ledger.association_for("npc", "door_slam"), -0.6)

    def test_spontaneous_recovery_rate_decays_toward_neutral(self):
        ledger = NPCConditioningLedger(associations={("npc", "crowd"): -0.8})
        profile = ConditioningProfile("npc", spontaneous_recovery_rate=0.1)
        ledger.advance(2, {"npc": profile})
        self.assertAlmostEqual(ledger.association_for("npc", "crowd"), -0.648)

    def test_decay_clock_is_independent_per_npc(self):
        ledger = NPCConditioningLedger(associations={
            ("npc-a", "cue"): 1.0, ("npc-b", "cue"): 1.0,
        })
        profile_a = ConditioningProfile("npc-a", spontaneous_recovery_rate=0.1)
        profile_b = ConditioningProfile("npc-b", spontaneous_recovery_rate=0.1)
        ledger.advance(1, {"npc-a": profile_a})
        ledger.advance(2, {"npc-b": profile_b})
        self.assertAlmostEqual(ledger.association_for("npc-a", "cue"), 0.9)
        self.assertAlmostEqual(ledger.association_for("npc-b", "cue"), 0.81)
        restored = NPCConditioningSnapshot.capture(ledger).restore()
        ledger.advance(3, {"npc-b": profile_b})
        restored.advance(3, {"npc-b": profile_b})
        self.assertEqual(restored.snapshot(), ledger.snapshot())

    def test_replay_is_idempotent_and_conflicts_rejected(self):
        ledger = NPCConditioningLedger()
        profile = ConditioningProfile("npc")
        args = dict(record_id="r", source_event_id="e", owner_id="npc",
                    cue="betrayal", tick=0, outcome=-1, intensity=1, profile=profile)
        first = ledger.learn(**args)
        self.assertEqual(ledger.learn(**args), first)
        with self.assertRaises(ValueError):
            ledger.learn(**{**args, "outcome": 1})

    def test_snapshot_round_trip(self):
        ledger = NPCConditioningLedger()
        ledger.learn(record_id="r", source_event_id="e", owner_id="npc",
                     cue="help", tick=0, outcome=1, intensity=0.8,
                     profile=ConditioningProfile("npc"))
        snapshot = NPCConditioningSnapshot.capture(ledger)
        self.assertEqual(snapshot.restore().snapshot(), ledger.snapshot())

    def test_unknown_modes_and_bad_owners_rejected(self):
        with self.assertRaises(ValueError):
            ConditioningProfile("npc", learning_rate=2)
        with self.assertRaises(ValueError):
            NPCConditioningLedger().learn(
                record_id="r", source_event_id="e", owner_id="npc", cue="x",
                tick=0, outcome=0, intensity=1, profile=ConditioningProfile("other"))

if __name__ == "__main__":
    unittest.main()
