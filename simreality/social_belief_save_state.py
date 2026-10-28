"""Versioned persistence for evidence histories and observer-specific beliefs."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from typing import Any
from .beliefs import BeliefLedger, Evidence
from .social_beliefs import SocialBeliefSystem
from .social_trust import SocialTrustLedger

def _unit(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return float(value)

def _evidence_dict(item: Evidence) -> dict[str, Any]:
    return {"evidence_id": item.evidence_id, "claim_id": item.claim_id, "source_id": item.source_id,
            "direction": item.direction, "strength": item.strength,
            "source_reliability": item.source_reliability, "observed_tick": item.observed_tick}

def _evidence_from(item: dict[str, Any]) -> Evidence:
    return Evidence(item["evidence_id"], item["claim_id"], item["source_id"], item["direction"],
                    _unit("evidence strength", item["strength"]),
                    _unit("evidence reliability", item["source_reliability"]), item["observed_tick"])

@dataclass(frozen=True)
class BeliefLedgerSnapshot:
    """Explicit claim-confidence priors and the complete effective evidence history."""
    priors: tuple[tuple[str, float], ...]
    evidence: tuple[Evidence, ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.priors, tuple) or not isinstance(self.evidence, tuple):
            raise ValueError("priors and evidence must be tuples")
        claims = [item[0] for item in self.priors]
        if any(not isinstance(x, str) or not x.strip() for x in claims) or claims != sorted(claims) or len(claims) != len(set(claims)):
            raise ValueError("prior claim IDs must be unique, non-empty, and sorted")
        for _, value in self.priors:
            _unit("prior confidence", value)
        if any(not isinstance(item, Evidence) for item in self.evidence):
            raise ValueError("evidence must contain Evidence records")
        ids = [item.evidence_id for item in self.evidence]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique and sorted")

    @classmethod
    def capture(cls, ledger: BeliefLedger):
        if not isinstance(ledger, BeliefLedger):
            raise TypeError("ledger must be a BeliefLedger")
        return cls(tuple(sorted(ledger._priors.items())), tuple(sorted(ledger._evidence.values(), key=lambda x: x.evidence_id)))

    def restore(self) -> BeliefLedger:
        ledger = BeliefLedger(dict(self.priors))
        ledger.add_many(self.evidence)
        return ledger

    def to_json(self) -> str:
        return json.dumps({"schema_version": self.SCHEMA_VERSION, "priors": [list(x) for x in self.priors],
                           "evidence": [_evidence_dict(x) for x in self.evidence]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported belief ledger schema version")
            priors = tuple(sorted(((x[0], _unit("prior confidence", x[1])) for x in raw["priors"]), key=lambda x: x[0]))
            evidence = tuple(sorted((_evidence_from(x) for x in raw["evidence"]), key=lambda x: x.evidence_id))
            return cls(priors, evidence)
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("belief ledger snapshot has an invalid structure") from exc

@dataclass(frozen=True)
class _ObserverSnapshot:
    observer_id: str
    ledger: BeliefLedgerSnapshot
    inputs: tuple[Evidence, ...]

@dataclass(frozen=True)
class SocialBeliefSnapshot:
    """Separate observer ledgers plus original inputs and sampled effective reliability."""
    observers: tuple[_ObserverSnapshot, ...]
    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.observers, tuple) or any(not isinstance(x, _ObserverSnapshot) for x in self.observers):
            raise ValueError("observers must be a tuple of observer snapshots")
        ids = [x.observer_id for x in self.observers]
        if any(not isinstance(x, str) or not x.strip() for x in ids) or ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("observer IDs must be unique, non-empty, and sorted")
        for observer in self.observers:
            input_ids = [x.evidence_id for x in observer.inputs]
            effective_ids = [x.evidence_id for x in observer.ledger.evidence]
            if input_ids != sorted(input_ids) or len(input_ids) != len(set(input_ids)) or set(input_ids) != set(effective_ids):
                raise ValueError("each effective evidence item needs one original input")

    @classmethod
    def capture(cls, system: SocialBeliefSystem):
        if not isinstance(system, SocialBeliefSystem):
            raise TypeError("system must be a SocialBeliefSystem")
        return cls(tuple(_ObserverSnapshot(
            observer_id, BeliefLedgerSnapshot.capture(system._ledgers[observer_id]),
            tuple(sorted(system._inputs.get(observer_id, {}).values(), key=lambda x: x.evidence_id)))
            for observer_id in sorted(system._ledgers)))

    def restore(self, trust: SocialTrustLedger) -> SocialBeliefSystem:
        if not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        system = SocialBeliefSystem(trust)
        for observer in self.observers:
            system._ledgers[observer.observer_id] = observer.ledger.restore()
            system._inputs[observer.observer_id] = {x.evidence_id: x for x in observer.inputs}
        return system

    def to_json(self) -> str:
        return json.dumps({"schema_version": self.SCHEMA_VERSION, "observers": [
            {"observer_id": x.observer_id, "ledger": json.loads(x.ledger.to_json()),
             "inputs": [_evidence_dict(item) for item in x.inputs]} for x in self.observers]},
            sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported social belief schema version")
            observers = []
            for item in raw["observers"]:
                observers.append(_ObserverSnapshot(
                    item["observer_id"],
                    BeliefLedgerSnapshot.from_json(json.dumps(item["ledger"], allow_nan=False)),
                    tuple(sorted((_evidence_from(x) for x in item["inputs"]), key=lambda x: x.evidence_id)),
                ))
            return cls(tuple(sorted(observers, key=lambda x: x.observer_id)))
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("social belief snapshot has an invalid structure") from exc
