import unittest

from simreality.identity_evolution import IdentityChangeProposal, NPCIdentityProfile
from simreality.identity_decisions import IdentityChangeDecision, IdentityDecisionLedger
from simreality.identity_decisions_save_state import IdentityDecisionSnapshot
from simreality.emotional_scars import EmotionalScar, NPCEmotionalScarLedger
from simreality.emotional_scar_identity import EmotionalScarIdentityAdapter, ScarIdentityPolicy
from simreality.world_events import WorldEventLedger


class IdentityDecisionTests(unittest.TestCase):
    def setUp(self):
        self.profile = NPCIdentityProfile("npc-a", {"trust": 0.2}, {"trust": 1.0})
        self.proposal = IdentityChangeProposal(
            "event-1", "npc-a", "policy-1", "trust", 0.2, 0.25, 0.05, 1.0, "participant"
        )

    def test_accepted_scar_informs_identity_proposal_without_mutating_traits(self):
        events = WorldEventLedger((WorldEventLedger.make_event(
            "event-scar", 2, "incident", participants=("npc-a",),
        ),))
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "scar-1", "npc-a", "event-scar", "memory-1", 3,
            "fear", "crowded-room", 0.8, 0.999,
        ))
        identities = IdentityDecisionLedger((self.profile,))
        policy = ScarIdentityPolicy(
            "fear-to-trust", "fear", "crowded-room", "trust",
            -0.05, minimum_severity=0.2, maximum_delta=0.05,
        )
        proposals = EmotionalScarIdentityAdapter.propose(
            scars, identities, events, (policy,), 4,
        )
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal.event_id, "event-scar")
        self.assertEqual(proposal.npc_id, "npc-a")
        self.assertEqual(proposal.axis, "trust")
        self.assertLess(proposal.delta, 0)
        self.assertEqual(identities.traits_for("npc-a")["trust"], 0.2)
        identities.decide(
            "scar-identity-decision", proposal, accepted=False,
            decision_tick=4, rationale="I do not want this experience to define my trust",
        )
        self.assertEqual(identities.traits_for("npc-a")["trust"], 0.2)
        self.assertFalse(identities.entries()[0].accepted)

    def test_scar_identity_proposals_respect_recovery_threshold_and_role(self):
        events = WorldEventLedger((WorldEventLedger.make_event(
            "event-scar", 2, "incident", witnesses=("npc-a",),
        ),))
        scars = NPCEmotionalScarLedger()
        scars.add_scar(EmotionalScar(
            "scar-1", "npc-a", "event-scar", "memory-1", 3,
            "fear", "crowded-room", 0.8, 0.999,
        ))
        scars.recover(
            recovery_id="recovery-1", scar_id="scar-1", owner_id="npc-a",
            tick=3, amount=0.7, method="support",
        )
        identities = IdentityDecisionLedger((self.profile,))
        policy = ScarIdentityPolicy(
            "fear-to-trust", "fear", "crowded-room", "trust",
            -0.05, minimum_severity=0.2, include_witnesses=False,
        )
        self.assertEqual(
            EmotionalScarIdentityAdapter.propose(scars, identities, events, (policy,), 4),
            (),
        )
        witness_policy = ScarIdentityPolicy(
            "fear-to-trust-witness", "fear", "crowded-room", "trust",
            -0.05, minimum_severity=0.05, include_witnesses=True,
        )
        proposal, = EmotionalScarIdentityAdapter.propose(
            scars, identities, events, (witness_policy,), 4,
        )
        self.assertEqual(proposal.role, "witness")
        self.assertLess(proposal.evidence_strength, 0.2)

    def test_ledger_rejects_invalid_decision_types_before_sorting(self):
        with self.assertRaisesRegex(TypeError, "IdentityChangeDecision"):
            IdentityDecisionLedger((self.profile,), decisions=(object(),))

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

    def test_decision_rejects_unrepresentably_large_numeric_values(self):
        with self.assertRaises(ValueError):
            IdentityChangeDecision("d", "e", "npc-a", "p", "trust", True, 1, "r",
                                   10**10000, 0.2, 0.0, 0.5, "participant")

    def test_invalid_decision_tick_rejected(self):
        with self.assertRaises(ValueError):
            IdentityChangeDecision.from_proposal(
                "d", self.proposal, accepted=True, decision_tick=-1, rationale="bad"
            )


if __name__ == "__main__":
    unittest.main()
