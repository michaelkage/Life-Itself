"""Individual NPC interpretation of events into directed relationship facets.

The event journal remains authoritative about what happened. This adapter only
converts caller-supplied impact axes, bias cues, and the observer's own beliefs
through that observer's explicit profile. It never assigns universal morality.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from .social_beliefs import SocialBeliefSystem
from .social_relationships import (
    RELATIONSHIP_FACETS, RelationshipChange, SocialRelationshipLedger,
)
from .world_events import WorldEventLedger


def _validate_response_map(name: str, value: Mapping[str, Mapping[str, float]]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    for source, responses in value.items():
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"{name} source keys must be non-empty strings")
        if not isinstance(responses, Mapping):
            raise ValueError(f"{name}[{source!r}] must be a mapping")
        for facet, weight in responses.items():
            if facet not in RELATIONSHIP_FACETS:
                raise ValueError(f"unknown relationship facet: {facet}")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValueError(f"{name}[{source!r}][{facet!r}] must be numeric")
            if not math.isfinite(weight) or not -1.0 <= weight <= 1.0:
                raise ValueError(f"{name}[{source!r}][{facet!r}] must be finite and in [-1, 1]")


def _validate_axes(name: str, values: Mapping[str, float]) -> None:
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping")
    for axis, value in values.items():
        if not isinstance(axis, str) or not axis.strip():
            raise ValueError(f"{name} axis names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name}[{axis!r}] must be numeric")
        if not math.isfinite(value) or not -1.0 <= value <= 1.0:
            raise ValueError(f"{name}[{axis!r}] must be finite and in [-1, 1]")


@dataclass(frozen=True)
class RelationshipInterpretationProfile:
    """One observer's learned response to values, bias cues, and belief claims.

    Each source axis maps to one or more relationship facets. Positive and
    negative coefficients are both meaningful. Profiles are deliberately
    observer-specific; two NPCs can react oppositely to identical evidence.
    """

    observer_id: str
    value_responses: Mapping[str, Mapping[str, float]]
    bias_responses: Mapping[str, Mapping[str, float]] | None = None
    claim_responses: Mapping[str, Mapping[str, float]] | None = None

    def __post_init__(self):
        if not isinstance(self.observer_id, str) or not self.observer_id.strip():
            raise ValueError("observer_id must be a non-empty string")
        _validate_response_map("value_responses", self.value_responses)
        _validate_response_map("bias_responses", self.bias_responses or {})
        _validate_response_map("claim_responses", self.claim_responses or {})


@dataclass(frozen=True)
class RelationshipInterpretationResult:
    event_id: str
    observer_id: str
    target_id: str
    tick: int
    contributions: tuple[tuple[str, str, float], ...]
    changes: tuple[RelationshipChange, ...]


class NPCRelationshipInterpreter:
    """Translate one observer's explicit interpretation into replay-safe changes."""

    def __init__(
        self,
        events: WorldEventLedger,
        relationships: SocialRelationshipLedger,
        beliefs: SocialBeliefSystem | None = None,
    ):
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(relationships, SocialRelationshipLedger):
            raise TypeError("relationships must be a SocialRelationshipLedger")
        if beliefs is not None and not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem or None")
        self.events = events
        self.relationships = relationships
        self.beliefs = beliefs
        self._results: dict[tuple[str, str, str], RelationshipInterpretationResult] = {}

    def interpret(
        self,
        event_id: str,
        observer_id: str,
        target_id: str,
        profile: RelationshipInterpretationProfile,
        *,
        value_impacts: Mapping[str, float],
        bias_cues: Mapping[str, float] | None = None,
    ) -> RelationshipInterpretationResult:
        if not isinstance(profile, RelationshipInterpretationProfile):
            raise TypeError("profile must be a RelationshipInterpretationProfile")
        if profile.observer_id != observer_id:
            raise ValueError("interpretation profile belongs to a different observer")
        if observer_id == target_id:
            raise ValueError("observer and target must be different NPCs")
        _validate_axes("value_impacts", value_impacts)
        _validate_axes("bias_cues", bias_cues or {})
        event = self.events.get(event_id)
        if observer_id not in event.witnesses:
            raise ValueError(f"{observer_id!r} is not recorded as a witness to {event_id!r}")
        if target_id not in event.participants:
            raise ValueError(f"{target_id!r} is not a participant in {event_id!r}")

        key = (event_id, observer_id, target_id)
        contributions: dict[tuple[str, str], float] = {}
        for axis in sorted(profile.value_responses):
            impact = value_impacts.get(axis, 0.0)
            for facet, coefficient in sorted(profile.value_responses[axis].items()):
                contributions[(facet, f"value:{axis}")] = impact * coefficient
        cues = bias_cues or {}
        for cue in sorted(profile.bias_responses or {}):
            strength = cues.get(cue, 0.0)
            for facet, coefficient in sorted(profile.bias_responses[cue].items()):
                contributions[(facet, f"bias:{cue}")] = strength * coefficient
        for claim_id in sorted(profile.claim_responses or {}):
            if self.beliefs is None:
                raise ValueError("claim responses require a SocialBeliefSystem")
            confidence = self.beliefs.get(observer_id, claim_id).confidence
            signed_confidence = 2.0 * confidence - 1.0
            for facet, coefficient in sorted(profile.claim_responses[claim_id].items()):
                contributions[(facet, f"belief:{claim_id}")] = signed_confidence * coefficient

        facet_totals = {facet: 0.0 for facet in RELATIONSHIP_FACETS}
        trace = []
        for (facet, source), amount in sorted(contributions.items()):
            facet_totals[facet] += amount
            trace.append((facet, source, amount))
        touched_facets = {facet for facet, _source in contributions}
        changes = []
        for facet in RELATIONSHIP_FACETS:
            if facet not in touched_facets:
                continue
            delta = min(1.0, max(-1.0, facet_totals[facet]))
            changes.append(RelationshipChange(
                change_id=f"relationship:{event_id}:{observer_id}:{target_id}:{facet}",
                source_event_id=event_id,
                observer_id=observer_id,
                target_id=target_id,
                tick=event.tick,
                facet=facet,
                delta=delta,
                evidence_tag="individual_interpretation",
            ))
        result = RelationshipInterpretationResult(
            event_id, observer_id, target_id, event.tick,
            tuple(trace), tuple(changes),
        )
        prior = self._results.get(key)
        if prior is not None:
            if prior != result:
                raise ValueError("event interpretation replayed with different profile or evidence")
            return prior
        # Preflight all IDs before applying any facet, preventing partial updates.
        for change in changes:
            existing = {item.change_id: item for item in self.relationships.snapshot()}.get(change.change_id)
            if existing is not None and existing != change:
                raise ValueError(f"relationship change ID reused: {change.change_id}")
        for change in changes:
            self.relationships.add(change)
        self._results[key] = result
        return result
