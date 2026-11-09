"""Bridge scheduled NPC routines to explicit, persistent travel journeys.

The adapter starts journeys for routines active at the supplied minute. It does
not execute the routine itself: the arrival event is the hand-off point for the
world driver to resolve the routine with its normal disruption and outcome rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .memory_routines import RoutineAvoidanceProfile
from .route_planning import PersonalRoutePlanner
from .routines import RoutineBook
from .travel import TravelTickAdapter


@dataclass(frozen=True)
class RoutineTravelRequest:
    routine_id: str
    owner_id: str
    journey_id: str | None
    origin: str
    destination: str
    status: str


class RoutineTravelAdapter:
    """Start deterministic journeys for active routine blocks."""

    def __init__(self, travel: TravelTickAdapter) -> None:
        if not isinstance(travel, TravelTickAdapter):
            raise TypeError("travel must be a TravelTickAdapter")
        self.travel = travel

    def start_due(
        self,
        tick: int,
        book: RoutineBook,
        minute_of_day: int,
        current_locations: Mapping[str, str],
        planner: PersonalRoutePlanner,
        *,
        closed_edge_ids: Iterable[str] = (),
        avoidance_profiles_by_owner: Mapping[str, Iterable[RoutineAvoidanceProfile]] | None = None,
    ) -> tuple[RoutineTravelRequest, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(book, RoutineBook):
            raise TypeError("book must be a RoutineBook")
        if isinstance(minute_of_day, bool) or not isinstance(minute_of_day, int) or not 0 <= minute_of_day < 1440:
            raise ValueError("minute_of_day must be an integer from 0 to 1439")
        if not isinstance(current_locations, Mapping):
            raise TypeError("current_locations must map NPC IDs to location IDs")
        for owner, location in current_locations.items():
            if not isinstance(owner, str) or not owner.strip() or not isinstance(location, str) or not location.strip():
                raise ValueError("current location entries require non-empty NPC and location IDs")
        if not isinstance(planner, PersonalRoutePlanner):
            raise TypeError("planner must be a PersonalRoutePlanner")
        supplied_profiles = avoidance_profiles_by_owner or {}
        if not isinstance(supplied_profiles, Mapping):
            raise TypeError("avoidance_profiles_by_owner must be a mapping")
        profiles = {}
        for owner, values in supplied_profiles.items():
            if not isinstance(owner, str) or not owner.strip():
                raise ValueError("avoidance profile owners must be non-empty strings")
            profile_values = tuple(values)
            if any(not isinstance(profile, RoutineAvoidanceProfile) or profile.owner_id != owner
                   for profile in profile_values):
                raise ValueError("avoidance profiles must be typed and scoped to their owner")
            profiles[owner] = profile_values
        closed = tuple(closed_edge_ids)

        requests = []
        for block in book.snapshot():
            if not block.start_minute <= minute_of_day < block.end_minute:
                continue
            if block.owner_id not in current_locations:
                raise ValueError(f"missing current location for routine owner: {block.owner_id}")
            origin = current_locations[block.owner_id]
            journey_id = f"routine:{tick}:{block.routine_id}"
            existing = self.travel.ledger.get(journey_id)
            if existing is not None:
                requests.append(RoutineTravelRequest(
                    block.routine_id, block.owner_id, journey_id, origin,
                    block.location_id, existing.status,
                ))
                continue
            active = next((journey for journey in self.travel.ledger.for_owner(block.owner_id)
                           if journey.status in ("travelling", "blocked", "unreachable")), None)
            if active is not None:
                requests.append(RoutineTravelRequest(
                    block.routine_id, block.owner_id, active.journey_id, origin,
                    block.location_id, "already_travelling",
                ))
                continue
            if origin == block.location_id:
                requests.append(RoutineTravelRequest(
                    block.routine_id, block.owner_id, None, origin,
                    block.location_id, "already_at_destination",
                ))
                continue
            plan = planner.plan(
                block.owner_id, origin, block.location_id,
                avoidance_profiles=profiles.get(block.owner_id, ()),
                closed_edge_ids=closed,
            )
            if not plan.found:
                requests.append(RoutineTravelRequest(
                    block.routine_id, block.owner_id, None, origin,
                    block.location_id, "unreachable",
                ))
                continue
            journey = self.travel.start(
                journey_id, block.owner_id, plan, tick, routine_id=block.routine_id,
            )
            requests.append(RoutineTravelRequest(
                block.routine_id, block.owner_id, journey.journey_id, origin,
                block.location_id, journey.status,
            ))
        return tuple(requests)
