"""SRE-Fluid ordered evidence gather: deterministic per-claim belief proposals.

The GPU-compatible pass mirrors BeliefLedger's recurrence over evidence that has
already been canonically ordered by (observed_tick, evidence_id). It proposes
confidence values only; the authoritative CPU ledger still owns provenance,
idempotency, history, and persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from typing import Iterable

CLAIM_SLOT_STRIDE = 32
EVIDENCE_EDGE_STRIDE = 16
GATHER_OUTPUT_STRIDE = 16
WORKGROUP_SIZE = 256


def _unit(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")


@dataclass(frozen=True)
class EvidenceEdge:
    evidence_id: str
    observed_tick: int
    strength: float
    source_reliability: float
    direction: int

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id must be a non-empty string")
        if isinstance(self.observed_tick, bool) or not isinstance(self.observed_tick, int) or self.observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")
        _unit(self.strength, "strength")
        _unit(self.source_reliability, "source_reliability")
        if isinstance(self.direction, bool) or self.direction not in (-1, 1):
            raise ValueError("direction must be +1 or -1")


@dataclass(frozen=True)
class ClaimEvidenceBatch:
    claim_id: str
    prior_confidence: float
    evidence: tuple[EvidenceEdge, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        _unit(self.prior_confidence, "prior_confidence")
        if any(not isinstance(item, EvidenceEdge) for item in self.evidence):
            raise TypeError("evidence must contain EvidenceEdge values")
        ids = [item.evidence_id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique within a claim batch")


@dataclass(frozen=True)
class GatherResult:
    claim_id: str
    confidence: float
    evidence_count: int


def _canonical_batches(batches: Iterable[ClaimEvidenceBatch]) -> tuple[ClaimEvidenceBatch, ...]:
    items = tuple(batches)
    if any(not isinstance(item, ClaimEvidenceBatch) for item in items):
        raise TypeError("batches must contain ClaimEvidenceBatch values")
    ids = [item.claim_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("claim IDs must be unique within a gather batch")
    evidence_ids = [edge.evidence_id for item in items for edge in item.evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidence IDs must be unique across a gather batch")
    return tuple(sorted(items, key=lambda item: item.claim_id))


def pack_evidence_gather(
    batches: Iterable[ClaimEvidenceBatch],
) -> tuple[bytes, bytes, tuple[str, ...]]:
    """Return packed claim slots, ordered evidence edges, and stable claim IDs.

    Each 32-byte slot stores a u32 edge offset/count plus its f32 prior.
    Each 16-byte edge stores strength, source reliability, signed direction,
    and padding. Evidence order is canonical per claim.
    """
    items = _canonical_batches(batches)
    slots = bytearray()
    edges = bytearray()
    for batch in items:
        ordered = sorted(batch.evidence, key=lambda item: (item.observed_tick, item.evidence_id))
        start = len(edges) // EVIDENCE_EDGE_STRIDE
        if start > 0xFFFFFFFF or len(ordered) > 0xFFFFFFFF - start:
            raise OverflowError("evidence gather edge indices exceed u32")
        slots.extend(struct.pack("<4I4f", start, len(ordered), 0, 0,
                                 batch.prior_confidence, 0.0, 0.0, 0.0))
        for item in ordered:
            edges.extend(struct.pack("<4f", item.strength, item.source_reliability,
                                     float(item.direction), 0.0))
    return bytes(slots), bytes(edges), tuple(item.claim_id for item in items)


def evaluate_gather_cpu(
    batches: Iterable[ClaimEvidenceBatch],
) -> tuple[GatherResult, ...]:
    """Mirror BeliefLedger's ordered confidence recurrence without mutating it."""
    items = _canonical_batches(batches)
    results = []
    for batch in items:
        confidence = float(batch.prior_confidence)
        ordered = sorted(batch.evidence, key=lambda item: (item.observed_tick, item.evidence_id))
        for item in ordered:
            influence = item.strength * item.source_reliability
            target = 1.0 if item.direction > 0 else 0.0
            confidence += (target - confidence) * influence
        results.append(GatherResult(batch.claim_id, min(1.0, max(0.0, confidence)),
                                    len(ordered)))
    return tuple(results)


def unpack_gather_outputs(
    claim_ids: tuple[str, ...], output: bytes | bytearray | memoryview,
) -> tuple[GatherResult, ...]:
    """Decode 16-byte result records and restore CPU-side claim identifiers."""
    if len(output) != len(claim_ids) * GATHER_OUTPUT_STRIDE:
        raise ValueError("gather output has an invalid byte length")
    results = []
    for index, claim_id in enumerate(claim_ids):
        confidence, count, reserved_a, reserved_b = struct.unpack_from(
            "<4f", output, index * GATHER_OUTPUT_STRIDE)
        if (not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0
                or not math.isfinite(count) or count < 0.0
                or count != math.floor(count) or count > 16_777_216
                or reserved_a != 0.0 or reserved_b != 0.0):
            raise ValueError("gather output contains an invalid result")
        results.append(GatherResult(claim_id, confidence, int(count)))
    return tuple(results)
