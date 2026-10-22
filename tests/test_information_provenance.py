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
