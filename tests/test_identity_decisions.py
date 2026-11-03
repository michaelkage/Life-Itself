import unittest

from simreality.identity_evolution import IdentityChangeProposal, NPCIdentityProfile
from simreality.identity_decisions import IdentityChangeDecision, IdentityDecisionLedger
from simreality.identity_decisions_save_state import IdentityDecisionSnapshot


class IdentityDecisionTests(unittest.TestCase):
    def setUp(self):
        self.profile = NPCIdentityProfile("npc-a", {"trust": 0.2}, {"trust": 1.0})
        self.proposal = IdentityChangeProposal(
            "event-1", "npc-a", "policy-1", "trust", 0.2, 0.25, 0.05, 1.0, "participant"
        )

    def test_accept_changes_trait_and_replay_is_idempotent(self):
        ledger = IdentityDecisionLedger((self.profile,))
        decision = IdentityChangeDecision.from_proposal(
            "decision-1", self.proposal, accepted=True, decision_tick=4, rationale="Convincing evidence"
        )
        ledger.record(decision)
        ledger.record(decision)
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.25)
        self.assertEqual(len(ledger.entries()), 1)

    def test_rejection_preserves_trait_but_remains_in_history(self):
        ledger = IdentityDecisionLedger((self.profile,))
        ledger.decide("decision-1", self.proposal, accepted=False, decision_tick=4, rationale="Disagrees")
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.2)
        self.assertEqual(ledger.entries()[0].accepted, False)

    def test_conflicting_replay_and_second_decision_are_rejected(self):
        ledger = IdentityDecisionLedger((self.profile,))
        decision = IdentityChangeDecision.from_proposal(
            "decision-1", self.proposal, accepted=True, decision_tick=4, rationale="yes"
        )
        ledger.record(decision)
        conflict = IdentityChangeDecision.from_proposal(
            "decision-1", self.proposal, accepted=False, decision_tick=4, rationale="no"
        )
        with self.assertRaises(ValueError):
            ledger.record(conflict)
        other = IdentityChangeDecision.from_proposal(
            "decision-2", self.proposal, accepted=False, decision_tick=4, rationale="no"
        )
        with self.assertRaises(ValueError):
            ledger.record(other)

    def test_snapshot_round_trip_preserves_accepted_traits_and_rejected_history(self):
        ledger = IdentityDecisionLedger((self.profile,))
        ledger.decide("d1", self.proposal, accepted=True, decision_tick=4, rationale="Accepted")
        second = IdentityChangeProposal(
            "event-2", "npc-a", "policy-1", "trust", 0.25, 0.3, 0.05, 0.8, "witness"
        )
        ledger.decide("d2", second, accepted=False, decision_tick=8, rationale="Rejected")
        encoded = IdentityDecisionSnapshot.capture(ledger).to_json()
        restored = IdentityDecisionSnapshot.from_json(encoded).restore()
        self.assertEqual(restored.traits_for("npc-a")["trust"], 0.25)
        self.assertEqual([d.accepted for d in restored.entries()], [True, False])
        self.assertEqual(IdentityDecisionSnapshot.capture(restored).to_json(), encoded)

    def test_snapshot_rejects_boolean_schema_version(self):
        encoded = IdentityDecisionSnapshot.capture(IdentityDecisionLedger((self.profile,))).to_json()
        malformed = encoded.replace('"schema_version":1', '"schema_version":true', 1)
        with self.assertRaisesRegex(ValueError, "schema"):
            IdentityDecisionSnapshot.from_json(malformed)

    def test_noncanonical_snapshot_rejected(self):
        encoded = IdentityDecisionSnapshot.capture(IdentityDecisionLedger((self.profile,))).to_json()
        with self.assertRaises(ValueError):
            IdentityDecisionSnapshot.from_json(encoded + " ")

    def test_record_many_is_atomic_when_one_decision_is_invalid(self):
        ledger = IdentityDecisionLedger((self.profile,))
        valid = IdentityChangeDecision.from_proposal(
            "d-valid", self.proposal, accepted=True, decision_tick=4, rationale="yes"
        )
        invalid = IdentityChangeDecision(
            "d-invalid", "event-2", "npc-a", "policy-2", "trust",
            True, 5, "bad baseline", 0.9, 0.95, 0.05, 1.0, "participant",
        )
        with self.assertRaises(ValueError):
            ledger.record_many((valid, invalid))
        self.assertEqual(ledger.entries(), ())
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.2)

    def test_record_many_replays_in_decision_time_order(self):
        ledger = IdentityDecisionLedger((self.profile,))
        first = IdentityChangeDecision(
            "d1", "event-1", "npc-a", "p1", "trust",
            True, 4, "first", 0.2, 0.25, 0.05, 1.0, "participant",
        )
        second = IdentityChangeDecision(
            "d2", "event-2", "npc-a", "p2", "trust",
            True, 5, "second", 0.25, 0.3, 0.05, 1.0, "participant",
        )
        ledger.record_many((second, first))
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.3)
        self.assertEqual([d.decision_id for d in ledger.entries()], ["d1", "d2"])

    def test_out_of_order_same_axis_decision_is_rejected_before_mutation(self):
        ledger = IdentityDecisionLedger((self.profile,))
        first = IdentityChangeDecision.from_proposal(
            "d-later", self.proposal, accepted=True, decision_tick=8, rationale="later"
        )
        ledger.record(first)
        earlier_proposal = IdentityChangeProposal(
            "event-earlier", "npc-a", "policy-earlier", "trust",
            0.25, 0.3, 0.05, 0.8, "participant",
        )
        earlier = IdentityChangeDecision.from_proposal(
            "d-earlier", earlier_proposal, accepted=True, decision_tick=7, rationale="earlier"
        )
        with self.assertRaisesRegex(ValueError, "decision order"):
            ledger.record(earlier)
        self.assertEqual(ledger.entries(), (first,))
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.25)

    def test_same_tick_decisions_use_snapshot_canonical_order(self):
        ledger = IdentityDecisionLedger((self.profile,))
        first = IdentityChangeDecision(
            "a-decision", "event-1", "npc-a", "p1", "trust",
            True, 4, "first", 0.2, 0.25, 0.05, 1.0, "participant",
        )
        second = IdentityChangeDecision(
            "z-decision", "event-2", "npc-a", "p2", "trust",
            True, 4, "second", 0.25, 0.3, 0.05, 1.0, "participant",
        )
        ledger.record(first)
        ledger.record(second)
        self.assertEqual(
            IdentityDecisionSnapshot.capture(ledger).restore().traits_for("npc-a")["trust"],
            0.3,
        )

    def test_record_many_keeps_chain_order_index_for_future_appends(self):
        ledger = IdentityDecisionLedger((self.profile,))
        first = IdentityChangeDecision(
            "d1", "event-1", "npc-a", "p1", "trust",
            True, 4, "first", 0.2, 0.25, 0.05, 1.0, "participant",
        )
        second = IdentityChangeDecision(
            "d2", "event-2", "npc-a", "p2", "trust",
            True, 5, "second", 0.25, 0.3, 0.05, 1.0, "participant",
        )
        ledger.record_many((second, first))
        third = IdentityChangeDecision(
            "d3", "event-3", "npc-a", "p3", "trust",
            True, 6, "third", 0.3, 0.35, 0.05, 1.0, "participant",
        )
        ledger.record(third)
        self.assertEqual(ledger.traits_for("npc-a")["trust"], 0.35)

    def test_snapshot_rejects_duplicate_or_unsorted_profile_entries(self):
        valid = IdentityDecisionSnapshot.capture(IdentityDecisionLedger((self.profile,)))
        profile = valid.profiles[0]
        duplicate_traits = (profile[0], (("trust", 0.2), ("trust", 0.2)), profile[2], profile[3])
        with self.assertRaises(ValueError):
            IdentityDecisionSnapshot((duplicate_traits,), ())
        unsorted_traits = (profile[0], (("z", 0.0), ("a", 0.0)), profile[2], profile[3])
        with self.assertRaises(ValueError):
            IdentityDecisionSnapshot((unsorted_traits,), ())

    def test_snapshot_rejects_malformed_profile_records_without_type_errors(self):
        valid = IdentityDecisionSnapshot.capture(IdentityDecisionLedger((self.profile,)))
        profile = valid.profiles[0]
        malformed_records = (
            ("npc-a", (("trust", 0.2), (None, 0.1)), profile[2], profile[3]),
            ("npc-a", (("trust", 0.2), (1, 0.1)), profile[2], profile[3]),
            ("npc-a", (("trust", 0.2),), profile[2]),
        )
        for malformed in malformed_records:
            with self.subTest(record=malformed), self.assertRaises(ValueError):
                IdentityDecisionSnapshot((malformed,), ())

    def test_snapshot_rejects_malformed_decision_records(self):
        valid = IdentityDecisionSnapshot.capture(IdentityDecisionLedger((self.profile,)))
        for malformed in (("decision-id",), (None,) + (None,) * 12):
            with self.subTest(record=malformed), self.assertRaises(ValueError):
                IdentityDecisionSnapshot(valid.profiles, (malformed,))

    def test_invalid_decision_tick_rejected(self):
        with self.assertRaises(ValueError):
            IdentityChangeDecision.from_proposal(
                "d", self.proposal, accepted=True, decision_tick=-1, rationale="bad"
            )


if __name__ == "__main__":
    unittest.main()
