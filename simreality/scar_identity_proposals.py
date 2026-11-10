"""Canonical persistence for scar-informed identity proposal provenance."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from .identity_evolution import IdentityChangeProposal


@dataclass(frozen=True)
class ScarIdentityProposalEvidence:
    proposal: IdentityChangeProposal
    scar_id: str
    base_policy_id: str
    emotion_axis: str
    cue_id: str
    evaluated_tick: int
    severity: float

    def __post_init__(self):
        if not isinstance(self.proposal, IdentityChangeProposal):
            raise TypeError("proposal must be IdentityChangeProposal")
        for name in ("scar_id", "base_policy_id", "emotion_axis", "cue_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if isinstance(self.evaluated_tick, bool) or not isinstance(self.evaluated_tick, int) or self.evaluated_tick < 0:
            raise ValueError("evaluated_tick must be non-negative")
        if isinstance(self.severity, bool) or not isinstance(self.severity, (int, float)) or not math.isfinite(self.severity) or not 0 <= self.severity <= 1:
            raise ValueError("severity must be finite and in [0, 1]")
        if self.proposal.policy_id != f"{self.base_policy_id}:{self.scar_id}":
            raise ValueError("proposal policy key must identify its source policy and scar")


class ScarIdentityProposalLedger:
    """Append-only, replay-safe archive of exact scar-informed proposals."""
    def __init__(self, records=()):
        self._records = {}
        for record in sorted(tuple(records), key=lambda r: (r.evaluated_tick, r.proposal.policy_id, r.proposal.npc_id)):
            self.record(record)

    def record(self, evidence):
        if not isinstance(evidence, ScarIdentityProposalEvidence):
            raise TypeError("evidence must be ScarIdentityProposalEvidence")
        key = (evidence.proposal.event_id, evidence.proposal.npc_id, evidence.proposal.policy_id)
        previous = self._records.get(key)
        if previous is not None and previous != evidence:
            raise ValueError("scar identity proposal key reused with different provenance")
        self._records[key] = evidence
        return evidence

    def record_many(self, evidence):
        candidate = ScarIdentityProposalLedger(self.entries())
        for item in evidence:
            candidate.record(item)
        self._records = candidate._records
        return tuple(self._records[(x.proposal.event_id, x.proposal.npc_id, x.proposal.policy_id)] for x in evidence)

    def entries(self):
        return tuple(sorted(self._records.values(), key=lambda r: (
            r.evaluated_tick, r.proposal.event_id, r.proposal.npc_id, r.proposal.policy_id)))

    def snapshot(self):
        return ScarIdentityProposalSnapshot.capture(self)

    @classmethod
    def from_snapshot(cls, snapshot):
        if not isinstance(snapshot, ScarIdentityProposalSnapshot):
            raise TypeError("snapshot must be ScarIdentityProposalSnapshot")
        return cls(snapshot.records)


@dataclass(frozen=True)
class ScarIdentityProposalSnapshot:
    records: tuple
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, ScarIdentityProposalLedger):
            raise TypeError("ledger must be ScarIdentityProposalLedger")
        return cls(tuple(ledger.entries()))

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(r, ScarIdentityProposalEvidence) for r in self.records):
            raise ValueError("invalid scar identity proposal records")
        keys = [(r.proposal.event_id, r.proposal.npc_id, r.proposal.policy_id) for r in self.records]
        if keys != sorted(keys, key=lambda k: next((r.evaluated_tick for r in self.records if (r.proposal.event_id, r.proposal.npc_id, r.proposal.policy_id) == k), 0)) and len(keys) != len(set(keys)):
            raise ValueError("duplicate scar identity proposal records")

    @staticmethod
    def _record(r):
        p = r.proposal
        return [p.event_id, p.npc_id, p.policy_id, p.axis, p.before, p.after, p.delta,
                p.evidence_strength, p.role, p.maximum_delta, r.scar_id, r.base_policy_id,
                r.emotion_axis, r.cue_id, r.evaluated_tick, r.severity]

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "records": [self._record(r) for r in self.records]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported scar identity proposal schema")
            records = []
            for row in raw["records"]:
                if not isinstance(row, list) or len(row) != 16:
                    raise ValueError("invalid scar identity proposal record")
                proposal = IdentityChangeProposal(*row[:10])
                records.append(ScarIdentityProposalEvidence(proposal, *row[10:]))
            result = cls(tuple(records))
            if result.to_json() != payload:
                raise ValueError("scar identity snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid scar identity proposal snapshot") from exc
