"""Campaign-owned, provenance-preserving knowledge shared across lives.

This ledger stores attributed evidence about world claims. It is deliberately
separate from PersonProfile memories and relationships: a later life may consult
the campaign record without inheriting another character's private experience.
Evidence is not ground truth; confidence is reconstructed from its provenance.
"""
from __future__ import annotations

import json

from .beliefs import BeliefLedger, BeliefState, Evidence


class CampaignKnowledgeLedger:
    """Append-only evidence ledger whose scope is the campaign, not one life."""

    def __init__(self, evidence=()):
        self._evidence: dict[str, Evidence] = {}
        for item in evidence:
            self.add(item)

    def add(self, evidence: Evidence) -> Evidence:
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance")
        prior = self._evidence.get(evidence.evidence_id)
        if prior is not None:
            if prior != evidence:
                raise ValueError(f"campaign evidence ID reused with different content: {evidence.evidence_id}")
            return prior
        self._evidence[evidence.evidence_id] = evidence
        return evidence

    def evidence_for(self, claim_id: str) -> tuple[Evidence, ...]:
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise ValueError("claim_id must be a non-empty string")
        return tuple(sorted(
            (item for item in self._evidence.values() if item.claim_id == claim_id),
            key=lambda item: (item.observed_tick, item.evidence_id),
        ))

    def belief(self, claim_id: str) -> BeliefState:
        items = self.evidence_for(claim_id)
        if not items:
            raise KeyError(claim_id)
        ledger = BeliefLedger()
        ledger.add_many(items)
        return ledger.get(claim_id)

    def snapshot(self) -> tuple[Evidence, ...]:
        return tuple(sorted(
            self._evidence.values(),
            key=lambda item: (item.observed_tick, item.evidence_id),
        ))

    def to_json(self) -> str:
        return json.dumps({
            "schema_version": 1,
            "evidence": [{
                "evidence_id": item.evidence_id,
                "claim_id": item.claim_id,
                "source_id": item.source_id,
                "direction": item.direction,
                "strength": item.strength,
                "source_reliability": item.source_reliability,
                "observed_tick": item.observed_tick,
            } for item in self.snapshot()],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "CampaignKnowledgeLedger":
        try:
            raw = json.loads(payload)
            if (not isinstance(raw, dict) or set(raw) != {"schema_version", "evidence"}
                    or raw["schema_version"] != 1 or not isinstance(raw["evidence"], list)):
                raise ValueError("invalid campaign knowledge snapshot")
            evidence = tuple(Evidence(**item) for item in raw["evidence"])
            result = cls(evidence)
            if result.to_json() != payload:
                raise ValueError("campaign knowledge snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid campaign knowledge snapshot") from exc
