"""Observer-specific interpretations of authoritative world events.

World events remain immutable facts. Authored per-NPC rules may interpret an
observed event differently, including incorrectly. This adapter emits a
learning proposal; a caller must explicitly decide whether to apply it.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .world_events import WorldEvent


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class EventInterpretationRule:
    rule_id: str
    event_type: str
    cue: str
    outcome: float
    intensity: float = 1.0
    mode: str = "reinforce"
    required_attributes: tuple[tuple[str, object], ...] = ()

    def __post_init__(self):
        for name in ("rule_id", "event_type", "cue"):
            _nonempty(getattr(self, name), name)
        if isinstance(self.outcome, bool) or not isinstance(self.outcome, (int, float)) or not math.isfinite(self.outcome) or not -1 <= self.outcome <= 1:
            raise ValueError("outcome must be finite and in [-1, 1]")
        if isinstance(self.intensity, bool) or not isinstance(self.intensity, (int, float)) or not math.isfinite(self.intensity) or not 0 <= self.intensity <= 1:
            raise ValueError("intensity must be finite and in [0, 1]")
        if self.mode not in ("reinforce", "extinguish"):
            raise ValueError("mode must be reinforce or extinguish")
        if not isinstance(self.required_attributes, tuple):
            raise ValueError("required_attributes must be a tuple")
        keys = []
        for item in self.required_attributes:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("required attributes must be key/value pairs")
            key, value = item
            _nonempty(key, "attribute key")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError("required attribute values must be scalar")
            keys.append(key)
        if len(keys) != len(set(keys)):
            raise ValueError("required attribute keys must be unique")
        if tuple(sorted(self.required_attributes)) != self.required_attributes:
            raise ValueError("required attributes must be sorted by key")


@dataclass(frozen=True)
class NPCInterpretationProfile:
    owner_id: str
    rules: tuple[EventInterpretationRule, ...]

    def __post_init__(self):
        _nonempty(self.owner_id, "owner_id")
        if not isinstance(self.rules, tuple) or any(not isinstance(rule, EventInterpretationRule) for rule in self.rules):
            raise TypeError("rules must be a tuple of EventInterpretationRule values")
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("interpretation rule IDs must be unique per NPC")


@dataclass(frozen=True)
class LearningProposal:
    owner_id: str
    source_event_id: str
    tick: int
    rule_id: str
    cue: str
    outcome: float
    intensity: float
    mode: str
    interpretation_label: str


class NPCEventInterpreter:
    """Create explicit, observer-specific learning proposals from witnessed facts."""

    @staticmethod
    def interpret(event: WorldEvent, profile: NPCInterpretationProfile) -> tuple[LearningProposal, ...]:
        if not isinstance(event, WorldEvent):
            raise TypeError("event must be a WorldEvent")
        if not isinstance(profile, NPCInterpretationProfile):
            raise TypeError("profile must be an NPCInterpretationProfile")
        if profile.owner_id not in event.participants + event.witnesses:
            return ()
        attributes = dict(event.attributes)
        proposals = []
        for rule in sorted(profile.rules, key=lambda item: item.rule_id):
            if rule.event_type != event.event_type:
                continue
            if any(attributes.get(key, object()) != value for key, value in rule.required_attributes):
                continue
            proposals.append(LearningProposal(
                profile.owner_id, event.event_id, event.tick, rule.rule_id,
                rule.cue, rule.outcome, rule.intensity, rule.mode,
                rule.rule_id,
            ))
        return tuple(proposals)
