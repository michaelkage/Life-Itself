"""Deterministic stress accumulation, coping, exhaustion, and recovery.

Stress is a separate psychological load, not an emotion axis or personality
trait. Inputs are explicit authored stressors and coping responses. Thresholds
produce assessments only; they never force an NPC action.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math


def _unit(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return float(value)


@dataclass(frozen=True)
class CopingProfile:
    owner_id: str
    reappraisal: float = 0.0
    distraction: float = 0.0
    support_seeking: float = 0.0
    suppression_cost: float = 0.0
    resilience: float = 0.0
    recovery_per_tick: float = 0.0
    exhaustion_threshold: float = 0.75
    breaking_point: float = 1.0

    def __post_init__(self):
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        for name in ("reappraisal", "distraction", "support_seeking",
                     "suppression_cost", "resilience", "recovery_per_tick",
                     "exhaustion_threshold", "breaking_point"):
            _unit(getattr(self, name), name)
        if self.exhaustion_threshold >= self.breaking_point:
            raise ValueError("exhaustion_threshold must be below breaking_point")

    def effectiveness(self, strategy: str) -> float:
        if strategy not in ("reappraisal", "distraction", "support_seeking", "suppression"):
            raise ValueError("unknown coping strategy")
        return self.suppression_cost if strategy == "suppression" else getattr(self, strategy)


@dataclass(frozen=True)
class StressRecord:
    record_id: str
    event_id: str
    owner_id: str
    tick: int
    stressor: float
    strategy: str
    reduction: float
    suppression_load: float
    net_change: float


@dataclass(frozen=True)
class StressAssessment:
    owner_id: str
    sampled_tick: int
    stress: float
    exhaustion: float
    at_exhaustion_threshold: bool
    at_breaking_point: bool
    recovery_capacity: float


class NPCStressLedger:
    """Append-only stressor history with deterministic decay and replay checks."""

    def __init__(self, *, current_tick: int = 0, initial_stress=None):
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        self.current_tick = current_tick
        self._stress = {}
        self._records = {}
        self._events = {}
        for owner_id, value in (initial_stress or {}).items():
            if not isinstance(owner_id, str) or not owner_id.strip():
                raise ValueError("stress owner IDs must be non-empty")
            self._stress[owner_id] = _unit(value, "initial stress")

    def stress_for(self, owner_id):
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        return self._stress.get(owner_id, 0.0)

    def apply_stressor(self, *, record_id: str, event_id: str, owner_id: str,
                       tick: int, intensity: float, profile: CopingProfile,
                       strategy: str = "reappraisal") -> StressRecord:
        for name, value in (("record_id", record_id), ("event_id", event_id), ("owner_id", owner_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(tick, int) or isinstance(tick, bool) or tick < self.current_tick:
            raise ValueError("stressor tick cannot precede current_tick")
        if not isinstance(profile, CopingProfile) or profile.owner_id != owner_id:
            raise ValueError("coping profile owner must match stress owner")
        intensity = _unit(intensity, "intensity")
        effectiveness = profile.effectiveness(strategy)
        prior = self._records.get(record_id)
        if prior is not None:
            expected = (event_id, owner_id, tick, intensity, strategy, effectiveness)
            actual = (prior.event_id, prior.owner_id, prior.tick, prior.stressor, prior.strategy,
                      prior.reduction / intensity if intensity else effectiveness)
            if actual != expected:
                raise ValueError("stress record ID reused with conflicting content")
            return prior
        event_key = (event_id, owner_id)
        if event_key in self._events:
            raise ValueError("world event already applied to this NPC's stress ledger")
            raise ValueError("stress event ID reused with conflicting owner or tick")
        # Advance passive recovery before applying a later stressor.
        self.advance(tick, {owner_id: profile})
        reduction = intensity * effectiveness
        suppression_load = intensity * profile.suppression_cost if strategy == "suppression" else 0.0
        net = max(0.0, intensity - reduction + suppression_load)
        value = min(1.0, self._stress.get(owner_id, 0.0) + net)
        self._stress[owner_id] = value
        record = StressRecord(record_id, event_id, owner_id, tick, intensity,
                              strategy, reduction, suppression_load, net)
        self._records[record_id] = record
        self._events[event_key] = tick
        return record

    def advance(self, tick: int, profiles=None):
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.current_tick:
            raise ValueError("tick must be an integer not earlier than current_tick")
        profiles = profiles or {}
        if not isinstance(profiles, dict):
            raise TypeError("profiles must be a mapping")
        for owner_id, profile in profiles.items():
            if not isinstance(profile, CopingProfile) or profile.owner_id != owner_id:
                raise ValueError("coping profiles must be keyed by their owner ID")
        elapsed = tick - self.current_tick
        if elapsed:
            for owner_id, value in tuple(self._stress.items()):
                profile = profiles.get(owner_id)
                if profile is None:
                    continue
                recovery = profile.recovery_per_tick * (1.0 + profile.resilience)
                self._stress[owner_id] = max(0.0, value - recovery * elapsed)
            self.current_tick = tick
        return tuple(self.assess(owner_id, profile) for owner_id, profile in sorted(profiles.items()))

    def assess(self, owner_id: str, profile: CopingProfile) -> StressAssessment:
        if not isinstance(profile, CopingProfile) or profile.owner_id != owner_id:
            raise ValueError("coping profile owner must match assessment owner")
        stress = self.stress_for(owner_id)
        return StressAssessment(
            owner_id, self.current_tick, stress,
            max(0.0, min(1.0, (stress - profile.exhaustion_threshold) /
                            (profile.breaking_point - profile.exhaustion_threshold))),
            stress >= profile.exhaustion_threshold,
            stress >= profile.breaking_point,
            min(1.0, profile.recovery_per_tick * (1.0 + profile.resilience)),
        )

    def records(self):
        return tuple(self._records[key] for key in sorted(self._records))

    def snapshot(self):
        return {
            "version": 1,
            "current_tick": self.current_tick,
            "stress": dict(sorted(self._stress.items())),
            "records": [
                {"record_id": r.record_id, "event_id": r.event_id,
                 "owner_id": r.owner_id, "tick": r.tick, "stressor": r.stressor,
                 "strategy": r.strategy, "reduction": r.reduction,
                 "suppression_load": r.suppression_load, "net_change": r.net_change}
                for r in self.records()
            ],
        }

    @classmethod
    def from_snapshot(cls, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported stress snapshot")
        ledger = cls(current_tick=data["current_tick"], initial_stress=data["stress"])
        for item in data["records"]:
            record = StressRecord(**item)
            event_key = (record.event_id, record.owner_id)
            if record.record_id in ledger._records or event_key in ledger._events:
                raise ValueError("duplicate stress replay identity")
            if record.tick > ledger.current_tick:
                raise ValueError("stress record cannot occur after current_tick")
            for name in ("stressor", "reduction", "suppression_load", "net_change"):
                _unit(getattr(record, name), name)
            if record.strategy not in ("reappraisal", "distraction", "support_seeking", "suppression"):
                raise ValueError("unknown persisted coping strategy")
            ledger._records[record.record_id] = record
            ledger._events[event_key] = record.tick
        return ledger


@dataclass(frozen=True)
class NPCStressSnapshot:
    payload: str

    def __post_init__(self):
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        raw = json.loads(self.payload)
        restored = NPCStressLedger.from_snapshot(raw)
        canonical = json.dumps(restored.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise ValueError("stress snapshot must use canonical JSON")

    @classmethod
    def capture(cls, ledger: NPCStressLedger):
        if not isinstance(ledger, NPCStressLedger):
            raise TypeError("ledger must be an NPCStressLedger")
        return cls(json.dumps(ledger.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))

    @classmethod
    def from_json(cls, payload: str):
        return cls(payload)

    def restore(self):
        return NPCStressLedger.from_snapshot(json.loads(self.payload))

    def to_json(self):
        return self.payload
