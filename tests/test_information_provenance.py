import math

import pytest

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


def test_relay_preserves_lineage_and_is_not_independent_evidence():
    ledger = InformationLedger()
    assert ledger.record(root_claim()).accepted
    assert ledger.relay("c1", "c2", "witness-b", "witness-c", 11, 0.8).accepted
    assert ledger.relay("c2", "c3", "witness-c", "witness-d", 12, 0.5).accepted

    assert ledger.find("c3").root_evidence_id == "evidence:camera-1"
    assert ledger.find("c2").confidence == pytest.approx(0.72)
    assert ledger.find("c3").confidence == pytest.approx(0.36)
    assert ledger.find("c3").hop_count == 2
    assert ledger.find("c3").kind is InformationKind.REPORT
    assert ledger.independent_evidence_count("person:7", "was_at:market") == 1


def test_distinct_root_evidence_counts_as_independent():
    ledger = InformationLedger()
    assert ledger.record(root_claim()).accepted
    assert ledger.record(root_claim(
        claim_id="c-other",
        root_evidence_id="evidence:independent-witness",
        source_entity_id="witness-x",
        recipient_entity_id="witness-y",
    )).accepted
    assert ledger.independent_evidence_count("person:7", "was_at:market") == 2


@pytest.mark.parametrize("claim", [
    root_claim(claim_id=""),
    root_claim(subject_key=""),
    root_claim(proposition_key=""),
    root_claim(root_evidence_id=""),
    root_claim(source_entity_id=""),
    root_claim(created_tick=-1),
    root_claim(confidence=float("nan")),
    root_claim(confidence=float("inf")),
    root_claim(confidence=-0.1),
    root_claim(confidence=1.1),
    root_claim(hop_count=1),
])
def test_invalid_root_claims_are_rejected(claim):
    assert not InformationLedger().record(claim).accepted


def test_duplicate_and_invalid_parentage_are_rejected():
    ledger = InformationLedger()
    assert ledger.record(root_claim()).accepted
    assert not ledger.record(root_claim()).accepted
    assert not ledger.record(root_claim(
        claim_id="orphan", parent_claim_id="missing", hop_count=1,
        source_entity_id="witness-b",
    )).accepted
    assert not ledger.record(root_claim(
        claim_id="forged", parent_claim_id="c1", hop_count=1,
        source_entity_id="witness-b", root_evidence_id="different-evidence",
    )).accepted
    assert not ledger.record(root_claim(
        claim_id="wrong-source", parent_claim_id="c1", hop_count=1,
        source_entity_id="someone-else",
    )).accepted
    assert not ledger.record(root_claim(
        claim_id="backwards", parent_claim_id="c1", hop_count=1,
        source_entity_id="witness-b", created_tick=9,
    )).accepted


@pytest.mark.parametrize("fidelity", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_relay_fidelity_is_rejected(fidelity):
    ledger = InformationLedger()
    assert ledger.record(root_claim()).accepted
    assert not ledger.relay("c1", "c2", "witness-b", "witness-c", 11, fidelity).accepted


def test_relay_requires_parent_recipient_to_be_sender():
    ledger = InformationLedger()
    assert ledger.record(root_claim()).accepted
    assert not ledger.relay("c1", "c2", "not-the-recipient", "witness-c", 11, 1.0).accepted


def test_correction_is_appended_without_rewriting_original_claim():
    ledger = InformationLedger()
    original = root_claim()
    assert ledger.record(original).accepted
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
    assert ledger.record(correction).accepted
    assert ledger.find("c1") == original
    assert ledger.find("correction-1").kind is InformationKind.CORRECTION
    assert len(ledger) == 2
    assert ledger.independent_evidence_count("person:7", "was_at:market") == 1
    assert math.isclose(ledger.find("c1").confidence, 0.9)
