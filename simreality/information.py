"""Append-only provenance for claims about simulated events.

Claims record what an actor reports or infers, not objective world truth.
Repeated relays retain their root evidence identity and therefore do not
become independent corroboration merely by being repeated.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


class InformationKind(str, Enum):
    OBSERVATION = "observation"
    REPORT = "report"
    INFERENCE = "inference"
    CORRECTION = "correction"


@dataclass(frozen=True)
class InformationClaim:
    claim_id: str
    subject_key: str
    proposition_key: str
    root_evidence_id: str
    source_entity_id: str
    recipient_entity_id: str = ""
    created_tick: int = 0
    confidence: float = 0.5
    hop_count: int = 0
    kind: InformationKind = InformationKind.OBSERVATION
    parent_claim_id: str = ""


@dataclass(frozen=True)
class ClaimResult:
    accepted: bool
    error: str = ""


class InformationLedger:
    """Deterministic claim ledger with explicit source lineage."""

    def __init__(self) -> None:
        self._claims: dict[str, InformationClaim] = {}

    def record(self, claim: InformationClaim) -> ClaimResult:
        if not claim.claim_id:
            return ClaimResult(False, "claim_id must not be empty")
        if not claim.subject_key:
            return ClaimResult(False, "subject_key must not be empty")
        if not claim.proposition_key:
            return ClaimResult(False, "proposition_key must not be empty")
        if not claim.root_evidence_id:
            return ClaimResult(False, "root_evidence_id must not be empty")
        if not claim.source_entity_id:
            return ClaimResult(False, "source_entity_id must not be empty")
        if claim.created_tick < 0:
            return ClaimResult(False, "created_tick must be non-negative")
        if not math.isfinite(claim.confidence) or not 0.0 <= claim.confidence <= 1.0:
            return ClaimResult(False, "confidence must be finite and within [0, 1]")
        if claim.claim_id in self._claims:
            return ClaimResult(False, "claim_id already exists")

        if not claim.parent_claim_id:
            if claim.hop_count != 0:
                return ClaimResult(False, "root claims must have hop_count zero")
        else:
            parent = self._claims.get(claim.parent_claim_id)
            if parent is None:
                return ClaimResult(False, "parent claim must be recorded before its child")
            if claim.root_evidence_id != parent.root_evidence_id:
                return ClaimResult(False, "a relay must preserve root evidence identity")
            if claim.source_entity_id != parent.recipient_entity_id:
                return ClaimResult(False, "relay source must be the parent claim recipient")
            if claim.created_tick < parent.created_tick:
                return ClaimResult(False, "claim time cannot precede its parent")
            if parent.hop_count >= 0xFFFFFFFF or claim.hop_count != parent.hop_count + 1:
                return ClaimResult(False, "relay hop_count must be parent hop_count plus one")

        self._claims[claim.claim_id] = claim
        return ClaimResult(True)

    def relay(
        self,
        parent_claim_id: str,
        new_claim_id: str,
        sender_entity_id: str,
        recipient_entity_id: str,
        created_tick: int,
        transmission_fidelity: float,
    ) -> ClaimResult:
        parent = self._claims.get(parent_claim_id)
        if parent is None:
            return ClaimResult(False, "parent claim does not exist")
        if not sender_entity_id or not recipient_entity_id:
            return ClaimResult(False, "relay sender and recipient must not be empty")
        if parent.recipient_entity_id != sender_entity_id:
            return ClaimResult(False, "sender must have received the parent claim")
        if (
            not math.isfinite(transmission_fidelity)
            or not 0.0 <= transmission_fidelity <= 1.0
        ):
            return ClaimResult(False, "transmission_fidelity must be finite and within [0, 1]")
        if parent.hop_count >= 0xFFFFFFFF:
            return ClaimResult(False, "hop_count limit reached")

        child = InformationClaim(
            claim_id=new_claim_id,
            subject_key=parent.subject_key,
            proposition_key=parent.proposition_key,
            root_evidence_id=parent.root_evidence_id,
            parent_claim_id=parent.claim_id,
            source_entity_id=sender_entity_id,
            recipient_entity_id=recipient_entity_id,
            created_tick=created_tick,
            confidence=parent.confidence * transmission_fidelity,
            hop_count=parent.hop_count + 1,
            kind=InformationKind.REPORT,
        )
        return self.record(child)

    def find(self, claim_id: str) -> InformationClaim | None:
        return self._claims.get(claim_id)

    def independent_evidence_count(self, subject_key: str, proposition_key: str) -> int:
        return len({
            claim.root_evidence_id
            for claim in self._claims.values()
            if claim.subject_key == subject_key and claim.proposition_key == proposition_key
        })

    def independent_evidence_strength(self, subject_key: str, proposition_key: str) -> float:
        """Combine distinct roots without allowing relays to amplify one root.

        This bounded support estimate is evidence strength, not objective truth.
        Each root contributes only its strongest recorded confidence.
        """
        strongest_by_root: dict[str, float] = {}
        for claim in self._claims.values():
            if claim.subject_key != subject_key or claim.proposition_key != proposition_key:
                continue
            strongest_by_root[claim.root_evidence_id] = max(
                strongest_by_root.get(claim.root_evidence_id, 0.0), claim.confidence
            )
        remaining = 1.0
        for confidence in strongest_by_root.values():
            remaining *= 1.0 - confidence
        return min(1.0, max(0.0, 1.0 - remaining))

    def independent_evidence_strength_for_recipient(
        self, subject_key: str, proposition_key: str, recipient_entity_id: str
    ) -> float:
        """Estimate support using only claims received by one NPC."""
        strongest_by_root: dict[str, float] = {}
        for claim in self._claims.values():
            if (
                claim.subject_key != subject_key
                or claim.proposition_key != proposition_key
                or claim.recipient_entity_id != recipient_entity_id
            ):
                continue
            strongest_by_root[claim.root_evidence_id] = max(
                strongest_by_root.get(claim.root_evidence_id, 0.0), claim.confidence
            )
        remaining = 1.0
        for confidence in strongest_by_root.values():
            remaining *= 1.0 - confidence
        return min(1.0, max(0.0, 1.0 - remaining))

    def __len__(self) -> int:
        return len(self._claims)

    @property
    def claims(self) -> dict[str, InformationClaim]:
        """A read-only-by-convention snapshot of claims, keyed by claim ID."""
        return dict(self._claims)
