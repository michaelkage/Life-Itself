import math
import unittest

from simreality.information import (
    InformationClaim,
    InformationKind,
    InformationLedger,
)


def root_claim(**overrides):
    values = dict(
        claim_id="c1",
        subject_key="person:7",
        proposition_key="was_at:market",
        root_evidence_id="evidence:camera-1",
        source_entity_id="witness-a",
        recipient_entity_id="witness-b",
        created_tick=10,
        confidence=0.9,
    )
    values.update(overrides)
    return InformationClaim(**values)


class InformationProvenanceTests(unittest.TestCase):
    def test_relay_preserves_lineage_and_is_not_independent_evidence(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim()).accepted)
        self.assertTrue(ledger.relay("c1", "c2", "witness-b", "witness-c", 11, 0.8).accepted)
        self.assertTrue(ledger.relay("c2", "c3", "witness-c", "witness-d", 12, 0.5).accepted)

        self.assertEqual(ledger.find("c3").root_evidence_id, "evidence:camera-1")
        self.assertAlmostEqual(ledger.find("c2").confidence, 0.72)
        self.assertAlmostEqual(ledger.find("c3").confidence, 0.36)
        self.assertEqual(ledger.find("c3").hop_count, 2)
        self.assertIs(ledger.find("c3").kind, InformationKind.REPORT)
        lineage = ledger.lineage_for_claim("c3")
        self.assertEqual(tuple(claim.claim_id for claim in lineage), ("c1", "c2", "c3"))
        self.assertEqual(lineage[0].root_evidence_id, lineage[-1].root_evidence_id)
        self.assertEqual(ledger.lineage_for_claim("missing"), ())
        self.assertEqual(tuple(claim.claim_id for claim in ledger.lineage_for_claim("c1")), ("c1",))
        # Returned claims are immutable values; querying lineage cannot mutate stored state.
        with self.assertRaises((AttributeError, TypeError)):
            lineage[0].confidence = 0.0
        self.assertAlmostEqual(ledger.find("c1").confidence, 0.9)
        self.assertEqual(ledger.independent_evidence_count("person:7", "was_at:market"), 1)
        # A long relay chain contributes only the strongest confidence for its root.
        self.assertAlmostEqual(ledger.independent_evidence_strength("person:7", "was_at:market"), 0.9)

    def test_claims_received_by_is_scoped_and_deterministically_ordered(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim(claim_id="later", created_tick=12)).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="earlier-z", created_tick=10, recipient_entity_id="witness-c"
        )).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="earlier-a",
            created_tick=10,
            recipient_entity_id="witness-c",
            root_evidence_id="evidence:camera-2",
            source_entity_id="witness-x",
        )).accepted)
        received = ledger.claims_received_by("witness-c")
        self.assertEqual(tuple(claim.claim_id for claim in received), ("earlier-a", "earlier-z"))
        self.assertEqual(ledger.claims_received_by("witness-b")[0].claim_id, "later")
        self.assertEqual(ledger.claims_received_by("unknown"), ())
        self.assertEqual(ledger.claims_received_by(""), ())

    def test_investigation_for_includes_received_claims_and_lineage(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim(claim_id="root", created_tick=10)).accepted)
        self.assertTrue(ledger.relay(
            "root", "relay", "witness-b", "witness-c", 11, 0.8
        ).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="conflict",
            proposition_key="was_not_at:market",
            root_evidence_id="evidence:driver",
            source_entity_id="driver",
            recipient_entity_id="witness-c",
            created_tick=12,
            confidence=0.7,
        )).accepted)

        investigation = ledger.investigation_for("witness-c")
        self.assertEqual(
            tuple(entry.claim.claim_id for entry in investigation),
            ("relay", "conflict"),
        )
        self.assertEqual(
            tuple(claim.claim_id for claim in investigation[0].lineage),
            ("root", "relay"),
        )
        self.assertEqual(
            tuple(claim.claim_id for claim in investigation[1].lineage),
            ("conflict",),
        )
        self.assertNotEqual(
            investigation[0].claim.proposition_key,
            investigation[1].claim.proposition_key,
        )
        # Repeated relays of one root remain one source of evidence; a separate
        # root can be considered independently without erasing the conflict.
        self.assertEqual(
            len({entry.claim.root_evidence_id for entry in investigation}),
            2,
        )
        self.assertEqual(ledger.investigation_for("uninformed"), ())

    def test_investigation_groups_keep_conflicts_separate_and_local(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim(
            claim_id="claim-a", recipient_entity_id="witness-c", confidence=0.8
        )).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="claim-a-copy", recipient_entity_id="witness-c", created_tick=11,
            confidence=0.6
        )).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="claim-b", recipient_entity_id="witness-c", created_tick=12,
            root_evidence_id="evidence:independent", source_entity_id="witness-x",
            confidence=0.5
        )).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="contrary", recipient_entity_id="witness-c", created_tick=13,
            proposition_key="was_not_at:market", root_evidence_id="evidence:contrary",
            source_entity_id="witness-y", confidence=0.7
        )).accepted)
        # This claim exists in the world but has not reached witness-c.
        self.assertTrue(ledger.record(root_claim(
            claim_id="unheard", recipient_entity_id="witness-z", created_tick=14,
            root_evidence_id="evidence:unheard", source_entity_id="witness-z",
            confidence=1.0
        )).accepted)

        groups = ledger.investigation_groups_for("witness-c")
        self.assertEqual(
            tuple(group.proposition_key for group in groups),
            ("was_at:market", "was_not_at:market"),
        )
        positive = groups[0]
        self.assertEqual(
            tuple(entry.claim.claim_id for entry in positive.entries),
            ("claim-a", "claim-a-copy", "claim-b"),
        )
        # Repeated root contributes once; the second distinct root contributes
        # independently. The unheard root must not leak into this NPC's view.
        self.assertEqual(positive.independent_evidence_count, 2)
        self.assertAlmostEqual(positive.evidence_strength, 1.0 - (0.2 * 0.5))
        self.assertEqual(groups[1].independent_evidence_count, 1)
        self.assertAlmostEqual(groups[1].evidence_strength, 0.7)
        self.assertEqual(ledger.investigation_groups_for("unknown"), ())

    def test_distinct_root_evidence_counts_as_independent(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim()).accepted)
        self.assertTrue(ledger.record(root_claim(
            claim_id="c-other",
            root_evidence_id="evidence:independent-witness",
            source_entity_id="witness-x",
            recipient_entity_id="witness-y",
        )).accepted)
        self.assertEqual(ledger.independent_evidence_count("person:7", "was_at:market"), 2)
        self.assertAlmostEqual(
            ledger.independent_evidence_strength("person:7", "was_at:market"), 1.0 - (0.1 * 0.1)
        )
        self.assertAlmostEqual(
            ledger.independent_evidence_strength_for_recipient("person:7", "was_at:market", "witness-b"), 0.9
        )
        self.assertEqual(
            ledger.independent_evidence_strength_for_recipient("person:7", "was_at:market", "uninformed"), 0.0
        )

    def test_invalid_root_claims_are_rejected(self):
        invalid_claims = [
            root_claim(claim_id=""),
            root_claim(subject_key=""),
            root_claim(proposition_key=""),
            root_claim(root_evidence_id=""),
            root_claim(source_entity_id=""),
            root_claim(recipient_entity_id=""),
            root_claim(created_tick=-1),
            root_claim(confidence=float("nan")),
            root_claim(confidence=float("inf")),
            root_claim(confidence=-0.1),
            root_claim(confidence=1.1),
            root_claim(hop_count=1),
        ]
        for claim in invalid_claims:
            with self.subTest(claim=claim):
                self.assertFalse(InformationLedger().record(claim).accepted)

    def test_duplicate_and_invalid_parentage_are_rejected(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim()).accepted)
        self.assertFalse(ledger.record(root_claim()).accepted)
        invalid_children = [
            root_claim(claim_id="orphan", parent_claim_id="missing", hop_count=1,
                       source_entity_id="witness-b"),
            root_claim(claim_id="forged", parent_claim_id="c1", hop_count=1,
                       source_entity_id="witness-b", root_evidence_id="different-evidence"),
            root_claim(claim_id="wrong-source", parent_claim_id="c1", hop_count=1,
                       source_entity_id="someone-else"),
            root_claim(claim_id="backwards", parent_claim_id="c1", hop_count=1,
                       source_entity_id="witness-b", created_tick=9),
        ]
        for claim in invalid_children:
            with self.subTest(claim=claim):
                self.assertFalse(ledger.record(claim).accepted)

    def test_invalid_relay_fidelity_is_rejected(self):
        for fidelity in (-0.1, 1.1, float("nan"), float("inf")):
            with self.subTest(fidelity=fidelity):
                ledger = InformationLedger()
                self.assertTrue(ledger.record(root_claim()).accepted)
                self.assertFalse(ledger.relay(
                    "c1", "c2", "witness-b", "witness-c", 11, fidelity
                ).accepted)

    def test_relay_requires_parent_recipient_to_be_sender(self):
        ledger = InformationLedger()
        self.assertTrue(ledger.record(root_claim()).accepted)
        self.assertFalse(ledger.relay(
            "c1", "c2", "not-the-recipient", "witness-c", 11, 1.0
        ).accepted)

    def test_correction_is_appended_without_rewriting_original_claim(self):
        ledger = InformationLedger()
        original = root_claim()
        self.assertTrue(ledger.record(original).accepted)
        correction = InformationClaim(
            claim_id="correction-1",
            subject_key=original.subject_key,
            proposition_key="was_not_at:market",
            root_evidence_id="evidence:followup-interview",
            source_entity_id="witness-a",
            recipient_entity_id="witness-b",
            created_tick=13,
            confidence=0.95,
            kind=InformationKind.CORRECTION,
        )
        self.assertTrue(ledger.record(correction).accepted)
        self.assertEqual(ledger.find("c1"), original)
        self.assertIs(ledger.find("correction-1").kind, InformationKind.CORRECTION)
        self.assertEqual(len(ledger), 2)
        self.assertEqual(ledger.independent_evidence_count("person:7", "was_at:market"), 1)
        self.assertTrue(math.isclose(ledger.find("c1").confidence, 0.9))

    def test_conflicting_accounts_remain_separate_propositions(self):
        ledger = InformationLedger()
        unsafe = root_claim()
        self.assertTrue(ledger.record(unsafe).accepted)
        conflicting = root_claim(
            claim_id="conflicting-account",
            proposition_key="was_not_at:market",
            root_evidence_id="evidence:independent-driver",
            source_entity_id="driver",
            recipient_entity_id="witness-b",
            created_tick=12,
            confidence=0.8,
            kind=InformationKind.REPORT,
        )
        self.assertTrue(ledger.record(conflicting).accepted)

        # Contradiction is preserved for later interpretation, not resolved by
        # the ledger into an objective verdict or a universal morality score.
        self.assertEqual(ledger.independent_evidence_count("person:7", "was_at:market"), 1)
        self.assertEqual(ledger.independent_evidence_count("person:7", "was_not_at:market"), 1)
        self.assertAlmostEqual(
            ledger.independent_evidence_strength_for_recipient(
                "person:7", "was_at:market", "witness-b"
            ), 0.9
        )
        self.assertAlmostEqual(
            ledger.independent_evidence_strength_for_recipient(
                "person:7", "was_not_at:market", "witness-b"
            ), 0.8
        )
        self.assertEqual(
            ledger.independent_evidence_strength_for_recipient(
                "person:7", "was_not_at:market", "uninformed"
            ), 0.0
        )


if __name__ == "__main__":
    unittest.main()
