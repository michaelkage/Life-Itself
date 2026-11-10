"""Presence- and opportunity-gated witness eligibility for world events.

This is an assessment layer, not a visibility simulator. The world driver must
supply which candidates had a genuine opportunity to observe an event.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .presence import PresenceLedger
from .world_events import WorldEvent


@dataclass(frozen=True)
class WitnessPresenceAssessment:
    witness_id: str
    eligible: bool
    reason: str


@dataclass(frozen=True)
class PresenceWitnessResolution:
    event_id: str
    tick: int
    location_id: str
    assessments: tuple[WitnessPresenceAssessment, ...]

    @property
    def eligible_witnesses(self) -> tuple[str, ...]:
        return tuple(item.witness_id for item in self.assessments if item.eligible)


class PresenceWitnessAdapter:
    """Reject impossible witness candidates without inventing perception."""

    def __init__(self, presence: PresenceLedger):
        if not isinstance(presence, PresenceLedger):
            raise TypeError("presence must be a PresenceLedger")
        self.presence = presence

    def resolve(
        self,
        event: WorldEvent,
        candidate_ids: Iterable[str],
        opportunities: Mapping[str, bool],
        *,
        location_attribute: str = "location_id",
    ) -> PresenceWitnessResolution:
        if not isinstance(event, WorldEvent):
            raise TypeError("event must be a WorldEvent")
        if not isinstance(location_attribute, str) or not location_attribute.strip():
            raise ValueError("location_attribute must be a non-empty string")
        attributes = dict(event.attributes)
        location_id = attributes.get(location_attribute)
        if not isinstance(location_id, str) or not location_id.strip():
            raise ValueError(f"event must provide a non-empty {location_attribute!r} attribute")
        candidates = tuple(candidate_ids)
        if any(not isinstance(owner, str) or not owner.strip() for owner in candidates):
            raise ValueError("candidate IDs must be non-empty strings")
        if len(candidates) != len(set(candidates)):
            raise ValueError("candidate IDs must be unique")
        if not isinstance(opportunities, Mapping):
            raise TypeError("opportunities must map candidate IDs to booleans")
        if any(owner not in candidates for owner in opportunities):
            raise ValueError("opportunity map contains a non-candidate NPC")
        if any(not isinstance(value, bool) for value in opportunities.values()):
            raise ValueError("opportunity values must be booleans")

        assessments = []
        for owner in sorted(candidates):
            record = self.presence.get(owner)
            if record is None:
                eligible, reason = False, "no_recorded_presence"
            elif record.status != "at_location":
                eligible, reason = False, "not_at_location"
            elif record.location_id != location_id:
                eligible, reason = False, "at_different_location"
            elif opportunities.get(owner) is not True:
                eligible, reason = False, "no_observation_opportunity"
            else:
                eligible, reason = True, "eligible"
            assessments.append(WitnessPresenceAssessment(owner, eligible, reason))
        return PresenceWitnessResolution(event.event_id, event.tick, location_id, tuple(assessments))
