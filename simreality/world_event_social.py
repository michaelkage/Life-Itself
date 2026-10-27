"""Explicit adapter from authoritative world events to NPC interpretations."""
from __future__ import annotations

from typing import Iterable

from .social_consequences import (
    ObservedClaim,
    SocialConsequenceRecorder,
    SocialConsequenceResult,
    WitnessedSocialEvent,
)
from .world_events import WorldEventLedger


class WorldEventSocialAdapter:
    """Record per-witness social consequences for an existing world event.

    The event journal supplies the shared event identity, tick, actor participation
    and witness list. The caller supplies the witness's interpretation; no global
    moral meaning is inferred. One observer's interpretation cannot overwrite
    another observer's result.
    """

    def __init__(self, events: WorldEventLedger, consequences: SocialConsequenceRecorder) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(consequences, SocialConsequenceRecorder):
            raise TypeError("consequences must be a SocialConsequenceRecorder")
        self.events = events
        self.consequences = consequences

    def record_interpretation(
        self,
        event_id: str,
        observer_id: str,
        actor_id: str,
        trust_direction: int,
        trust_strength: float,
        claims: Iterable[ObservedClaim] = (),
    ) -> SocialConsequenceResult:
        """Apply one witness's explicit interpretation of a recorded event."""
        event = self.events.get(event_id)
        if observer_id not in event.witnesses:
            raise ValueError(f"{observer_id!r} is not recorded as a witness to {event_id!r}")
        if actor_id not in event.participants:
            raise ValueError(f"{actor_id!r} is not a participant in {event_id!r}")
        interpreted = WitnessedSocialEvent(
            event_id=f"{event.event_id}:observer:{observer_id}",
            observer_id=observer_id,
            actor_id=actor_id,
            observed_tick=event.tick,
            trust_direction=trust_direction,
            trust_strength=trust_strength,
            claims=tuple(claims),
        )
        return self.consequences.record(interpreted)
