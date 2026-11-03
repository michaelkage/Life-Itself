"""Witness-specific recall from authoritative event facts.

Recall is a lossy, observer-conditioned projection: it never edits the
objective event and never invents facts. Attention weights and supplied
encoding samples are explicit inputs, so replay is deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .world_events import Scalar, WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class RecallDetail:
    """A named event fact eligible for witness encoding."""

    detail_id: str
    attribute_key: str
    category: str
    salience: float = 0.5

    def __post_init__(self) -> None:
        for name in ("detail_id", "attribute_key", "category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not math.isfinite(self.salience) or not 0.0 <= self.salience <= 1.0:
            raise ValueError("salience must be finite and in [0, 1]")


@dataclass(frozen=True)
class WitnessRecallProfile:
    """Stable observer factors; values are multipliers, not personality labels."""

    witness_id: str
    attention: tuple[tuple[str, float], ...] = ()
    encoding_strength: float = 1.0
    recall_threshold: float = 0.25

    def __post_init__(self) -> None:
        if not isinstance(self.witness_id, str) or not self.witness_id.strip():
            raise ValueError("witness_id must be a non-empty string")
        if not math.isfinite(self.encoding_strength) or not 0.0 <= self.encoding_strength <= 1.0:
            raise ValueError("encoding_strength must be finite and in [0, 1]")
        if not math.isfinite(self.recall_threshold) or not 0.0 <= self.recall_threshold <= 1.0:
            raise ValueError("recall_threshold must be finite and in [0, 1]")
        keys = [key for key, _ in self.attention]
        if len(keys) != len(set(keys)) or keys != sorted(keys):
            raise ValueError("attention keys must be unique and sorted")
        for key, weight in self.attention:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("attention category must be non-empty")
            if not math.isfinite(weight) or not 0.0 <= weight <= 2.0:
                raise ValueError("attention weights must be finite and in [0, 2]")

    def attention_for(self, category: str) -> float:
        return dict(self.attention).get(category, 1.0)


@dataclass(frozen=True)
class RecalledDetail:
    detail_id: str
    attribute_key: str
    value: Scalar
    confidence: float


@dataclass(frozen=True)
class WitnessRecall:
    event_id: str
    witness_id: str
    event_tick: int
    details: tuple[RecalledDetail, ...]
    omitted_detail_ids: tuple[str, ...]


class WitnessRecallAdapter:
    """Build and cache one deterministic recall record per event/witness pair."""

    def __init__(self, events: WorldEventLedger) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        self.events = events
        self._processed: dict[tuple[str, str], tuple[WitnessRecall, tuple[tuple[str, float], ...]]] = {}

    def recall(
        self,
        event_id: str,
        profile: WitnessRecallProfile,
        details: tuple[RecallDetail, ...],
        encoding_samples: Mapping[str, float],
    ) -> WitnessRecall:
        event = self.events.get(event_id)
        if profile.witness_id not in event.witnesses:
            raise ValueError(f"{profile.witness_id!r} is not recorded as a witness to {event_id!r}")
        if not isinstance(details, tuple) or any(not isinstance(d, RecallDetail) for d in details):
            raise TypeError("details must be a tuple of RecallDetail")
        if len({d.detail_id for d in details}) != len(details):
            raise ValueError("detail IDs must be unique")
        attributes = dict(event.attributes)
        if any(d.attribute_key not in attributes for d in details):
            raise ValueError("every recall detail must reference an event attribute")
        samples = tuple(sorted(encoding_samples.items()))
        if set(encoding_samples) != {d.detail_id for d in details}:
            raise ValueError("encoding_samples must contain exactly one sample per detail")
        for detail_id, sample in samples:
            if not isinstance(detail_id, str) or not detail_id:
                raise ValueError("sample detail IDs must be non-empty strings")
            if isinstance(sample, bool) or not isinstance(sample, (int, float)) or not math.isfinite(sample) or not 0.0 <= sample <= 1.0:
                raise ValueError("encoding samples must be finite numbers in [0, 1]")
        key = (event_id, profile.witness_id)
        if key in self._processed:
            cached, previous_samples = self._processed[key]
            if previous_samples != samples:
                raise ValueError("event/witness recall replayed with conflicting samples")
            return cached

        recalled: list[RecalledDetail] = []
        omitted: list[str] = []
        for detail in sorted(details, key=lambda d: d.detail_id):
            confidence = min(1.0, detail.salience * profile.attention_for(detail.category) * profile.encoding_strength)
            if encoding_samples[detail.detail_id] <= confidence and confidence >= profile.recall_threshold:
                recalled.append(RecalledDetail(detail.detail_id, detail.attribute_key, attributes[detail.attribute_key], confidence))
            else:
                omitted.append(detail.detail_id)
        result = WitnessRecall(event_id, profile.witness_id, event.tick, tuple(recalled), tuple(omitted))
        self._processed[key] = (result, samples)
        return result

    def snapshot(self) -> tuple[WitnessRecall, ...]:
        return tuple(value[0] for _, value in sorted(self._processed.items()))
