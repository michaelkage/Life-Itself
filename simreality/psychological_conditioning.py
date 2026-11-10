"""Event-sourced, owner-specific associative learning for NPC conditioning.

Only explicitly supplied cues and outcomes are learned. Associations influence
future consideration signals; this module never infers trauma, diagnoses an NPC,
or forces a behavioral response.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


def _unit(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return float(value)


def _identifier(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class ConditioningProfile:
    owner_id: str
    learning_rate: float = 0.25
    extinction_rate: float = 0.05
    spontaneous_recovery_rate: float = 0.0

    def __post_init__(self):
        _identifier(self.owner_id, "owner_id")
        for field in ("learning_rate", "extinction_rate", "spontaneous_recovery_rate"):
            _unit(getattr(self, field), field)


@dataclass(frozen=True)
class ConditioningRecord:
    record_id: str
    source_event_id: str
    owner_id: str
    cue: str
    tick: int
    outcome: float
    intensity: float
    mode: str
    before: float
    after: float


@dataclass(frozen=True)
class ConditionedResponse:
    owner_id: str
    cue: str
    sampled_tick: int
    association: float
    response_strength: float
    direction: str


class NPCConditioningLedger:
    """Append-only associative learning with deterministic decay and replay."""

    def __init__(self, *, current_tick=0, associations=None):
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        self.current_tick = current_tick
        self._associations = {}
        self._records = {}
        self._events = {}
        for key, value in (associations or {}).items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise ValueError("association keys must be (owner_id, cue) pairs")
            owner, cue = key
            _identifier(owner, "owner_id")
            _identifier(cue, "cue")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("association values must be finite and in [-1, 1]")
            self._associations[(owner, cue)] = float(value)

    def association_for(self, owner_id, cue):
        _identifier(owner_id, "owner_id")
        _identifier(cue, "cue")
        return self._associations.get((owner_id, cue), 0.0)

    def learn(self, *, record_id, source_event_id, owner_id, cue, tick,
              outcome, intensity, profile, mode="reinforce"):
        for name, value in (("record_id", record_id), ("source_event_id", source_event_id),
                            ("owner_id", owner_id), ("cue", cue)):
            _identifier(value, name)
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.current_tick:
            raise ValueError("learning tick cannot precede current_tick")
        if not isinstance(profile, ConditioningProfile) or profile.owner_id != owner_id:
            raise ValueError("conditioning profile owner must match learner")
        if mode not in ("reinforce", "extinguish"):
            raise ValueError("mode must be reinforce or extinguish")
        if isinstance(outcome, bool) or not isinstance(outcome, (int, float)) or not math.isfinite(outcome) or not -1 <= outcome <= 1:
            raise ValueError("outcome must be finite and in [-1, 1]")
        intensity = _unit(intensity, "intensity")
        prior = self._records.get(record_id)
        signature = (source_event_id, owner_id, cue, tick, float(outcome), intensity, mode)
        if prior is not None:
            existing = (prior.source_event_id, prior.owner_id, prior.cue, prior.tick,
                        prior.outcome, prior.intensity, prior.mode)
            if existing != signature:
                raise ValueError("conditioning record ID reused with conflicting content")
            return prior
        event_key = (source_event_id, owner_id, cue)
        if event_key in self._events:
            raise ValueError("source event already conditioned this NPC on this cue")
        self.advance(tick, {owner_id: profile})
        key = (owner_id, cue)
        before = self._associations.get(key, 0.0)
        rate = profile.learning_rate if mode == "reinforce" else profile.extinction_rate
        target = float(outcome) if mode == "reinforce" else 0.0
        after = max(-1.0, min(1.0, before + (target - before) * rate * intensity))
        self._associations[key] = after
        record = ConditioningRecord(record_id, source_event_id, owner_id, cue,
                                    tick, float(outcome), intensity, mode, before, after)
        self._records[record_id] = record
        self._events[event_key] = record_id
        return record

    def advance(self, tick, profiles=None):
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.current_tick:
            raise ValueError("tick must be an integer not earlier than current_tick")
        profiles = profiles or {}
        if not isinstance(profiles, dict):
            raise TypeError("profiles must be a mapping")
        for owner, profile in profiles.items():
            if not isinstance(profile, ConditioningProfile) or profile.owner_id != owner:
                raise ValueError("profiles must be keyed by matching owner IDs")
        elapsed = tick - self.current_tick
        if elapsed:
            for (owner, cue), value in tuple(self._associations.items()):
                profile = profiles.get(owner)
                if profile is None or profile.spontaneous_recovery_rate == 0:
                    continue
                factor = max(0.0, 1.0 - profile.spontaneous_recovery_rate) ** elapsed
                self._associations[(owner, cue)] = value * factor
            self.current_tick = tick
        return tuple(self.assess(owner, cue) for owner, profile in sorted(profiles.items())
                     for cue in sorted(c for o, c in self._associations if o == owner))

    def assess(self, owner_id, cue):
        value = self.association_for(owner_id, cue)
        return ConditionedResponse(owner_id, cue, self.current_tick, value,
                                   abs(value), "approach" if value > 0 else
                                   "avoid" if value < 0 else "neutral")

    def records(self):
        return tuple(self._records[key] for key in sorted(self._records))

    def snapshot(self):
        return {
            "version": 1,
            "current_tick": self.current_tick,
            "associations": [
                {"owner_id": owner, "cue": cue, "value": value}
                for (owner, cue), value in sorted(self._associations.items())
            ],
            "records": [
                {"record_id": r.record_id, "source_event_id": r.source_event_id,
                 "owner_id": r.owner_id, "cue": r.cue, "tick": r.tick,
                 "outcome": r.outcome, "intensity": r.intensity, "mode": r.mode,
                 "before": r.before, "after": r.after}
                for r in self.records()
            ],
        }

    @classmethod
    def from_snapshot(cls, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported conditioning snapshot")
        associations = {}
        for item in data["associations"]:
            key = (item["owner_id"], item["cue"])
            if key in associations:
                raise ValueError("duplicate persisted conditioning association")
            associations[key] = item["value"]
        ledger = cls(current_tick=data["current_tick"], associations=associations)
        for item in data["records"]:
            record = ConditioningRecord(**item)
            if record.record_id in ledger._records:
                raise ValueError("duplicate conditioning record ID")
            if record.tick > ledger.current_tick:
                raise ValueError("conditioning record cannot occur after current_tick")
            _unit(record.intensity, "intensity")
            if not -1 <= record.outcome <= 1 or record.mode not in ("reinforce", "extinguish"):
                raise ValueError("invalid persisted conditioning outcome")
            if not -1 <= record.before <= 1 or not -1 <= record.after <= 1:
                raise ValueError("persisted association values must be in [-1, 1]")
            event_key = (record.source_event_id, record.owner_id, record.cue)
            if event_key in ledger._events:
                raise ValueError("duplicate conditioning source event")
            ledger._records[record.record_id] = record
            ledger._events[event_key] = record.record_id
        return ledger


@dataclass(frozen=True)
class NPCConditioningSnapshot:
    payload: str

    def __post_init__(self):
        import json
        if not isinstance(self.payload, str):
            raise TypeError("payload must be a string")
        restored = NPCConditioningLedger.from_snapshot(json.loads(self.payload))
        canonical = json.dumps(restored.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload:
            raise ValueError("conditioning snapshot must use canonical JSON")

    @classmethod
    def capture(cls, ledger):
        import json
        if not isinstance(ledger, NPCConditioningLedger):
            raise TypeError("ledger must be an NPCConditioningLedger")
        return cls(json.dumps(ledger.snapshot(), sort_keys=True, separators=(",", ":"), allow_nan=False))

    @classmethod
    def from_json(cls, payload):
        return cls(payload)

    def restore(self):
        import json
        return NPCConditioningLedger.from_snapshot(json.loads(self.payload))

    def to_json(self):
        return self.payload
