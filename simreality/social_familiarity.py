"""Directional familiarity and recognition readiness from confirmed encounters.

Familiarity is not trust, affection, agreement, or proof of identity. The
world driver supplies explicit exposure strengths for each observer/target
direction. Recognition additionally requires an explicit identity cue.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping

from .presence_encounters import PresenceEncounter, PresenceEncounterLedger


@dataclass(frozen=True)
class FamiliarityObservation:
    observation_id: str
    encounter_id: str
    observer_id: str
    target_id: str
    tick: int
    strength: float

    def __post_init__(self):
        for name in ("observation_id", "encounter_id", "observer_id", "target_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.observer_id == self.target_id:
            raise ValueError("an NPC cannot become familiar with themselves")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if (isinstance(self.strength, bool) or not isinstance(self.strength, (int, float))
                or not math.isfinite(self.strength) or not 0 <= self.strength <= 1):
            raise ValueError("strength must be finite and in [0, 1]")


@dataclass(frozen=True)
class RecognitionAssessment:
    observer_id: str
    target_id: str
    familiarity: float
    threshold: float
    identity_cue_available: bool
    recognized: bool
    reason: str


class SocialFamiliarityLedger:
    """Store directional exposure history independently from social trust."""

    def __init__(self, observations: Iterable[FamiliarityObservation] = ()):
        self._observations: dict[str, FamiliarityObservation] = {}
        for item in observations:
            if not isinstance(item, FamiliarityObservation):
                raise TypeError("observations must contain FamiliarityObservation values")
            if item.observation_id in self._observations:
                raise ValueError(f"duplicate familiarity observation: {item.observation_id}")
            self._observations[item.observation_id] = item

    def add(self, observation: FamiliarityObservation) -> FamiliarityObservation:
        if not isinstance(observation, FamiliarityObservation):
            raise TypeError("observation must be a FamiliarityObservation")
        prior = self._observations.get(observation.observation_id)
        if prior is not None:
            if prior != observation:
                raise ValueError(f"familiarity observation ID reused: {observation.observation_id}")
            return prior
        self._observations[observation.observation_id] = observation
        return observation

    def snapshot(self) -> tuple[FamiliarityObservation, ...]:
        return tuple(sorted(self._observations.values(),
                            key=lambda x: (x.tick, x.observation_id)))

    def observations_for(self, observer_id: str, target_id: str) -> tuple[FamiliarityObservation, ...]:
        return tuple(x for x in self.snapshot()
                     if x.observer_id == observer_id and x.target_id == target_id)

    def familiarity(self, observer_id: str, target_id: str, *, through_tick: int | None = None) -> float:
        if not isinstance(observer_id, str) or not observer_id.strip() or not isinstance(target_id, str) or not target_id.strip():
            raise ValueError("observer and target IDs must be non-empty")
        if observer_id == target_id:
            raise ValueError("observer and target must be different NPCs")
        if through_tick is not None and (isinstance(through_tick, bool) or not isinstance(through_tick, int) or through_tick < 0):
            raise ValueError("through_tick must be a non-negative integer or None")
        remaining = 1.0
        for item in self.observations_for(observer_id, target_id):
            if through_tick is None or item.tick <= through_tick:
                remaining *= 1.0 - item.strength
        return 1.0 - remaining

    def assess_recognition(
        self, observer_id: str, target_id: str, *,
        identity_cue_available: bool, threshold: float = 0.5,
        through_tick: int | None = None,
    ) -> RecognitionAssessment:
        if not isinstance(identity_cue_available, bool):
            raise ValueError("identity_cue_available must be a boolean")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
            raise ValueError("threshold must be finite and in [0, 1]")
        value = self.familiarity(observer_id, target_id, through_tick=through_tick)
        if not identity_cue_available:
            recognized, reason = False, "no_identity_cue"
        elif value < threshold:
            recognized, reason = False, "insufficient_familiarity"
        else:
            recognized, reason = True, "familiar_enough_with_identity_cue"
        return RecognitionAssessment(observer_id, target_id, value, float(threshold),
                                     identity_cue_available, recognized, reason)


class PresenceFamiliarityAdapter:
    """Turn confirmed encounters into explicitly weighted directional exposure."""

    def __init__(self, encounters: PresenceEncounterLedger,
                 ledger: SocialFamiliarityLedger | None = None):
        if not isinstance(encounters, PresenceEncounterLedger):
            raise TypeError("encounters must be a PresenceEncounterLedger")
        if ledger is not None and not isinstance(ledger, SocialFamiliarityLedger):
            raise TypeError("ledger must be a SocialFamiliarityLedger or None")
        self.encounters = encounters
        self.ledger = ledger or SocialFamiliarityLedger()

    def observe_encounter(self, encounter_id: str,
                          strengths: Mapping[tuple[str, str], float]) -> tuple[FamiliarityObservation, ...]:
        encounter = self.encounters.get(encounter_id)
        if encounter is None:
            raise KeyError(f"unknown encounter: {encounter_id}")
        if not isinstance(strengths, Mapping):
            raise TypeError("strengths must map (observer_id, target_id) pairs to exposure strengths")
        a, b = encounter.participants
        expected = {(a, b), (b, a)}
        if set(strengths) != expected:
            raise ValueError("both directional exposure strengths must be supplied exactly once")
        # Construct and validate both directions before mutating either one.
        proposed = tuple(
            FamiliarityObservation(
                f"familiarity:{encounter_id}:{observer}:{target}",
                encounter_id, observer, target, encounter.tick,
                strengths[(observer, target)],
            )
            for observer, target in sorted(expected)
        )
        return tuple(self.ledger.add(item) for item in proposed)


@dataclass(frozen=True)
class SocialFamiliaritySnapshot:
    observations: tuple[FamiliarityObservation, ...]

    SCHEMA_VERSION = 1

    def __post_init__(self):
        if not isinstance(self.observations, tuple) or any(not isinstance(x, FamiliarityObservation) for x in self.observations):
            raise ValueError("observations must contain FamiliarityObservation records")
        ids = [x.observation_id for x in self.observations]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("familiarity observations must be uniquely sorted by ID")

    @classmethod
    def capture(cls, ledger: SocialFamiliarityLedger):
        if not isinstance(ledger, SocialFamiliarityLedger):
            raise TypeError("ledger must be a SocialFamiliarityLedger")
        return cls(tuple(sorted(ledger.snapshot(), key=lambda x: x.observation_id)))

    def restore(self):
        return SocialFamiliarityLedger(self.observations)

    def to_json(self):
        return json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "observations": [{
                "observation_id": x.observation_id, "encounter_id": x.encounter_id,
                "observer_id": x.observer_id, "target_id": x.target_id,
                "tick": x.tick, "strength": x.strength,
            } for x in self.observations],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported familiarity schema version")
            records = tuple(sorted((FamiliarityObservation(**item) for item in raw["observations"]),
                                   key=lambda x: x.observation_id))
            result = cls(records)
            if result.to_json() != payload:
                raise ValueError("familiarity snapshot must use canonical JSON")
            return result
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid familiarity snapshot") from exc
