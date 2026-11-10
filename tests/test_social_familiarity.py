import unittest

from simreality.presence_encounters import PresenceEncounter, PresenceEncounterLedger
from simreality.social_familiarity import (
    FamiliarityObservation, PresenceFamiliarityAdapter,
    SocialFamiliarityLedger, SocialFamiliaritySnapshot,
)


class SocialFamiliarityTests(unittest.TestCase):
    def setup_encounter(self):
        encounter = PresenceEncounter("meeting-1", 3, "office", ("alice", "bob"))
        ledger = PresenceEncounterLedger((encounter,))
        return ledger, PresenceFamiliarityAdapter(ledger)

    def test_directional_exposure_and_recognition_require_identity_cue(self):
        _, adapter = self.setup_encounter()
        adapter.observe_encounter("meeting-1", {("alice", "bob"): 0.7, ("bob", "alice"): 0.2})
        self.assertAlmostEqual(adapter.ledger.familiarity("alice", "bob"), 0.7)
        self.assertAlmostEqual(adapter.ledger.familiarity("bob", "alice"), 0.2)
        no_cue = adapter.ledger.assess_recognition("alice", "bob", identity_cue_available=False)
        self.assertFalse(no_cue.recognized)
        self.assertEqual(no_cue.reason, "no_identity_cue")
        with_cue = adapter.ledger.assess_recognition("alice", "bob", identity_cue_available=True)
        self.assertTrue(with_cue.recognized)

    def test_repeated_encounters_compound_without_becoming_trust(self):
        ledger, adapter = self.setup_encounter()
        adapter.observe_encounter("meeting-1", {("alice", "bob"): 0.5, ("bob", "alice"): 0.25})
        ledger._records["meeting-2"] = PresenceEncounter("meeting-2", 4, "office", ("alice", "bob"))
        adapter.observe_encounter("meeting-2", {("alice", "bob"): 0.5, ("bob", "alice"): 0.25})
        self.assertAlmostEqual(adapter.ledger.familiarity("alice", "bob"), 0.75)
        self.assertAlmostEqual(adapter.ledger.familiarity("bob", "alice"), 0.4375)
        self.assertEqual(adapter.ledger.observations_for("alice", "bob")[0].tick, 3)

    def test_replay_is_idempotent_and_conflicts_rejected(self):
        _, adapter = self.setup_encounter()
        strengths = {("alice", "bob"): 0.4, ("bob", "alice"): 0.6}
        first = adapter.observe_encounter("meeting-1", strengths)
        second = adapter.observe_encounter("meeting-1", strengths)
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "reused"):
            adapter.observe_encounter("meeting-1", {("alice", "bob"): 0.5, ("bob", "alice"): 0.6})

    def test_unknown_encounter_and_missing_direction_rejected(self):
        _, adapter = self.setup_encounter()
        with self.assertRaises(KeyError):
            adapter.observe_encounter("unknown", {})
        with self.assertRaisesRegex(ValueError, "both directional"):
            adapter.observe_encounter("meeting-1", {("alice", "bob"): 0.5})

    def test_historical_familiarity_and_snapshot_round_trip(self):
        _, adapter = self.setup_encounter()
        adapter.observe_encounter("meeting-1", {("alice", "bob"): 0.5, ("bob", "alice"): 0.25})
        adapter.ledger.add(FamiliarityObservation(
            "later", "meeting-2", "alice", "bob", 8, 0.4
        ))
        self.assertAlmostEqual(adapter.ledger.familiarity("alice", "bob", through_tick=3), 0.5)
        payload = SocialFamiliaritySnapshot.capture(adapter.ledger).to_json()
        restored = SocialFamiliaritySnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), adapter.ledger.snapshot())
        self.assertEqual(SocialFamiliaritySnapshot.capture(restored).to_json(), payload)


if __name__ == "__main__":
    unittest.main()
