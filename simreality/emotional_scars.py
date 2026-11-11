"""Persistent emotional scars with gradual recovery and cue-triggered appraisal.

Scars are explicit, owner-scoped records linked to an autobiographical memory
and authoritative event. Their severity decays slowly, can be reduced by
explicit recovery actions, and produces read-only responses to exact cues.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


def _text(name, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _unit(name, value, *, allow_zero=True):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or value > 1
            or (not allow_zero and value == 0)):
        interval = "[0, 1]" if allow_zero else "(0, 1]"
        raise ValueError(f"{name} must be finite and in {interval}")
    return float(value)


@dataclass(frozen=True)
class EmotionalScar:
    scar_id: str
    owner_id: str
    source_event_id: str
    source_memory_id: str
    created_tick: int
    emotion_axis: str
    cue_id: str
    initial_severity: float
    retained_per_tick: float = 0.999

    def __post_init__(self):
        for name in ("scar_id", "owner_id", "source_event_id", "source_memory_id",
                     "emotion_axis", "cue_id"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if isinstance(self.created_tick, bool) or not isinstance(self.created_tick, int) or self.created_tick < 0:
            raise ValueError("created_tick must be a non-negative integer")
        object.__setattr__(self, "initial_severity", _unit("initial_severity", self.initial_severity))
        object.__setattr__(self, "retained_per_tick", _unit("retained_per_tick", self.retained_per_tick, allow_zero=False))


@dataclass(frozen=True)
class ScarRecoveryRecord:
    recovery_id: str
    scar_id: str
    owner_id: str
    tick: int
    amount: float
    method: str

    def __post_init__(self):
        for name in ("recovery_id", "scar_id", "owner_id", "method"):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        object.__setattr__(self, "amount", _unit("amount", self.amount, allow_zero=False))


@dataclass(frozen=True)
class EmotionalScarContribution:
    scar_id: str
    source_event_id: str
    source_memory_id: str
    emotion_axis: str
    cue_id: str
    severity: float
    exposure: float
    intensity: float


@dataclass(frozen=True)
class EmotionalScarResponse:
    owner_id: str
    sampled_tick: int
    intensities: tuple[tuple[str, float], ...]
    contributions: tuple[EmotionalScarContribution, ...]


class NPCEmotionalScarLedger:
    """Append-only scar and recovery history with deterministic derived severity."""

    def __init__(self, *, current_tick: int = 0):
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        self.current_tick = current_tick
        self._scars: dict[str, EmotionalScar] = {}
        self._source_keys: dict[tuple[str, str, str, str], str] = {}
        self._recoveries: dict[str, ScarRecoveryRecord] = {}

    def scars(self, owner_id: str | None = None):
        items = self._scars.values()
        if owner_id is not None:
            _text("owner_id", owner_id)
            items = (item for item in items if item.owner_id == owner_id)
        return tuple(sorted(items, key=lambda x: (x.created_tick, x.scar_id)))

    def recoveries(self, owner_id: str | None = None):
        items = self._recoveries.values()
        if owner_id is not None:
            _text("owner_id", owner_id)
            items = (item for item in items if item.owner_id == owner_id)
        return tuple(sorted(items, key=lambda x: (x.tick, x.recovery_id)))

    def add_scar(self, scar: EmotionalScar):
        if not isinstance(scar, EmotionalScar):
            raise TypeError("scar must be an EmotionalScar")
        prior = self._scars.get(scar.scar_id)
        if prior is not None:
            if prior != scar:
                raise ValueError("scar ID reused with conflicting content")
            return prior
        if scar.created_tick < self.current_tick:
            raise ValueError("new scars cannot be inserted before current_tick")
        source_key = (scar.owner_id, scar.source_event_id, scar.emotion_axis, scar.cue_id)
        if source_key in self._source_keys:
            raise ValueError("source event already created this owner's scar for that axis and cue")
        self._scars[scar.scar_id] = scar
        self._source_keys[source_key] = scar.scar_id
        self.current_tick = max(self.current_tick, scar.created_tick)
        return scar

    def severity_for(self, scar_id: str, tick: int | None = None) -> float:
        if scar_id not in self._scars:
            raise KeyError(scar_id)
        scar = self._scars[scar_id]
        tick = self.current_tick if tick is None else tick
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < scar.created_tick:
            raise ValueError("severity tick must be an integer at or after scar creation")
        severity = scar.initial_severity
        cursor = scar.created_tick
        for recovery in self.recoveries(scar.owner_id):
            if recovery.scar_id != scar_id or recovery.tick > tick:
                continue
            severity *= scar.retained_per_tick ** (recovery.tick - cursor)
            if recovery.amount > severity + 1e-12:
                raise ValueError("recovery history exceeds scar severity")
            severity = max(0.0, severity - recovery.amount)
            cursor = recovery.tick
        return max(0.0, severity * (scar.retained_per_tick ** (tick - cursor)))

    def recover(self, *, recovery_id: str, scar_id: str, owner_id: str,
                tick: int, amount: float, method: str) -> ScarRecoveryRecord:
        scar = self._scars.get(scar_id)
        if scar is None:
            raise KeyError(scar_id)
        if owner_id != scar.owner_id:
            raise ValueError("recovery owner must match scar owner")
        record = ScarRecoveryRecord(recovery_id, scar_id, owner_id, tick, amount, method)
        prior = self._recoveries.get(record.recovery_id)
        if prior is not None:
            if prior != record:
                raise ValueError("recovery ID reused with conflicting content")
            return prior
        if tick < self.current_tick:
            raise ValueError("recovery tick cannot precede current_tick")
        available = self.severity_for(scar_id, tick)
        if record.amount > available + 1e-12:
            raise ValueError("recovery amount exceeds remaining scar severity")
        self._recoveries[record.recovery_id] = record
        self.current_tick = max(self.current_tick, tick)
        return record

    def evaluate(self, owner_id: str, observed_cues: Mapping[str, float],
                 tick: int) -> EmotionalScarResponse:
        owner_id = _text("owner_id", owner_id)
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < self.current_tick:
            raise ValueError("evaluation tick cannot precede current_tick")
        if not isinstance(observed_cues, Mapping):
            raise TypeError("observed_cues must map cue IDs to exposure")
        exposures = {_text("cue_id", cue): _unit("exposure", value)
                     for cue, value in observed_cues.items()}
        contributions, totals = [], {}
        for scar in self.scars(owner_id):
            exposure = exposures.get(scar.cue_id, 0.0)
            if exposure <= 0:
                continue
            severity = self.severity_for(scar.scar_id, tick)
            intensity = min(1.0, severity * exposure)
            if intensity <= 0:
                continue
            contributions.append(EmotionalScarContribution(
                scar.scar_id, scar.source_event_id, scar.source_memory_id,
                scar.emotion_axis, scar.cue_id, severity, exposure, intensity,
            ))
            totals[scar.emotion_axis] = totals.get(scar.emotion_axis, 0.0) + intensity
        contributions.sort(key=lambda x: (x.scar_id, x.emotion_axis, x.cue_id))
        return EmotionalScarResponse(
            owner_id, tick,
            tuple(sorted((axis, min(1.0, value)) for axis, value in totals.items())),
            tuple(contributions),
        )

    def snapshot(self):
        return {
            "version": 1,
            "current_tick": self.current_tick,
            "scars": [
                {"scar_id": s.scar_id, "owner_id": s.owner_id,
                 "source_event_id": s.source_event_id, "source_memory_id": s.source_memory_id,
                 "created_tick": s.created_tick, "emotion_axis": s.emotion_axis,
                 "cue_id": s.cue_id, "initial_severity": s.initial_severity,
                 "retained_per_tick": s.retained_per_tick}
                for s in self.scars()
            ],
            "recoveries": [
                {"recovery_id": r.recovery_id, "scar_id": r.scar_id,
                 "owner_id": r.owner_id, "tick": r.tick,
                 "amount": r.amount, "method": r.method}
                for r in self.recoveries()
            ],
        }

    @classmethod
    def from_snapshot(cls, data):
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("unsupported emotional scar snapshot")
        ledger = cls(current_tick=0)
        scars = tuple(EmotionalScar(**item) for item in data.get("scars", ()))
        recoveries = tuple(ScarRecoveryRecord(**item) for item in data.get("recoveries", ()))
        # Replay one chronological stream. Restoring all scars first advances
        # current_tick past older recovery records when a later scar was created.
        timeline = [
            (scar.created_tick, 0, scar.scar_id, scar)
            for scar in scars
        ] + [
            (record.tick, 1, record.recovery_id, record)
            for record in recoveries
        ]
        for _, kind, _, item in sorted(timeline, key=lambda entry: entry[:3]):
            if kind == 0:
                ledger.add_scar(item)
            else:
                ledger.recover(
                    recovery_id=item.recovery_id, scar_id=item.scar_id,
                    owner_id=item.owner_id, tick=item.tick,
                    amount=item.amount, method=item.method,
                )
        target_tick = data.get("current_tick")
        if isinstance(target_tick, bool) or not isinstance(target_tick, int) or target_tick < ledger.current_tick:
            raise ValueError("scar snapshot current_tick is invalid")
        ledger.current_tick = target_tick
        if ledger.snapshot() != data:
            raise ValueError("scar snapshot is not canonical")
        return ledger
