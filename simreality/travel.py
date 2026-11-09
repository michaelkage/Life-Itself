"""Deterministic, explicit NPC travel progression over route graphs.

Travel costs are abstract simulation-time units. The world driver supplies each
NPC's per-tick travel budget and current road conditions; this module never
assumes a clock rate, traffic model, or physical movement system.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math
from typing import Iterable, Mapping

from .memory_routines import RoutineAvoidanceProfile
from .route_planning import PersonalRoutePlanner, RouteEdge, RoutePlan
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class TravelJourney:
    journey_id: str
    owner_id: str
    origin: str
    destination: str
    path: tuple[str, ...]
    edge_ids: tuple[str, ...]
    edge_index: int = 0
    edge_progress: float = 0.0
    elapsed_cost: float = 0.0
    status: str = "travelling"
    started_tick: int = 0
    arrived_tick: int | None = None
    routine_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("journey_id", "owner_id", "origin", "destination"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.path, tuple) or len(self.path) < 1 or self.path[0] != self.origin or self.path[-1] != self.destination:
            raise ValueError("path must be a non-empty location sequence from origin to destination")
        if not isinstance(self.edge_ids, tuple) or len(self.edge_ids) != len(self.path) - 1:
            raise ValueError("edge_ids must identify every consecutive path segment")
        if any(not isinstance(item, str) or not item.strip() for item in self.edge_ids):
            raise ValueError("edge IDs must be non-empty strings")
        if self.status not in ("travelling", "arrived", "blocked", "unreachable"):
            raise ValueError("invalid journey status")
        if isinstance(self.edge_index, bool) or not isinstance(self.edge_index, int) or not 0 <= self.edge_index <= len(self.edge_ids):
            raise ValueError("edge_index is outside the journey")
        for name in ("edge_progress", "elapsed_cost"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if isinstance(self.started_tick, bool) or not isinstance(self.started_tick, int) or self.started_tick < 0:
            raise ValueError("started_tick must be a non-negative integer")
        if self.arrived_tick is not None and (isinstance(self.arrived_tick, bool) or not isinstance(self.arrived_tick, int) or self.arrived_tick < self.started_tick):
            raise ValueError("arrived_tick must be a valid tick")
        if self.routine_id is not None and (not isinstance(self.routine_id, str) or not self.routine_id.strip()):
            raise ValueError("routine_id must be None or a non-empty string")
        if self.status == "arrived" and (self.edge_index != len(self.edge_ids) or self.arrived_tick is None):
            raise ValueError("arrived journeys must be complete and have arrived_tick")

    @property
    def current_location(self) -> str:
        if self.status == "arrived":
            return self.destination
        return self.path[self.edge_index]


@dataclass(frozen=True)
class TravelTickResult:
    tick: int
    journeys: tuple[TravelJourney, ...]
    arrivals: tuple[str, ...]
    blocked: tuple[str, ...]


def _tick_signature(tick: int, budgets: Mapping[str, float], closed: tuple[str, ...], multipliers: tuple[tuple[str, float], ...], replan_blocked: bool, avoidance_profiles: tuple[tuple[str, tuple[object, ...]], ...]) -> str:
    profiles = [(owner, [(p.location_id, p.strength, p.source_memory_indices, p.alternative_location_id) for p in values]) for owner, values in avoidance_profiles]
    return json.dumps({"tick": tick, "budgets": sorted(budgets.items()), "closed": closed,
                       "multipliers": multipliers, "replan_blocked": replan_blocked,
                       "avoidance_profiles": profiles}, sort_keys=True, separators=(",", ":"), allow_nan=False)


class TravelLedger:
    """Owner-scoped journey state and idempotent per-tick result history."""

    def __init__(self, journeys: Iterable[TravelJourney] = ()) -> None:
        self._journeys: dict[str, TravelJourney] = {}
        self._ticks: dict[int, tuple[str, TravelTickResult]] = {}
        for journey in journeys:
            self.add(journey)

    def add(self, journey: TravelJourney) -> TravelJourney:
        if not isinstance(journey, TravelJourney):
            raise TypeError("journey must be a TravelJourney")
        if journey.journey_id in self._journeys:
            if self._journeys[journey.journey_id] == journey:
                return journey
            raise ValueError(f"conflicting journey ID: {journey.journey_id}")
        if any(item.owner_id == journey.owner_id and item.status in ("travelling", "blocked", "unreachable")
               for item in self._journeys.values()):
            raise ValueError(f"owner already has an active journey: {journey.owner_id}")
        self._journeys[journey.journey_id] = journey
        return journey

    def get(self, journey_id: str) -> TravelJourney | None:
        return self._journeys.get(journey_id)

    def for_owner(self, owner_id: str) -> tuple[TravelJourney, ...]:
        return tuple(sorted((j for j in self._journeys.values() if j.owner_id == owner_id), key=lambda j: j.journey_id))

    def snapshot(self) -> tuple[TravelJourney, ...]:
        return tuple(self._journeys[key] for key in sorted(self._journeys))

    def _apply_tick(self, tick: int, signature: str, result: TravelTickResult) -> TravelTickResult:
        existing = self._ticks.get(tick)
        if existing:
            if existing[0] != signature:
                raise ValueError(f"conflicting travel tick replay: {tick}")
            return existing[1]
        for journey in result.journeys:
            self._journeys[journey.journey_id] = journey
        self._ticks[tick] = (signature, result)
        return result

    def tick_snapshot(self) -> tuple[tuple[int, str, TravelTickResult], ...]:
        return tuple((tick, value[0], value[1]) for tick, value in sorted(self._ticks.items()))

    def _restore_tick(self, tick: int, signature: str, result: TravelTickResult) -> None:
        if tick in self._ticks:
            raise ValueError(f"duplicate travel tick: {tick}")
        self._ticks[tick] = (signature, result)


class TravelTickAdapter:
    """Advance journeys using explicit per-owner time budgets and road conditions."""

    def __init__(self, edges: Iterable[RouteEdge], ledger: TravelLedger | None = None) -> None:
        items = tuple(edges)
        if any(not isinstance(edge, RouteEdge) for edge in items):
            raise TypeError("edges must contain RouteEdge values")
        if len({edge.edge_id for edge in items}) != len(items):
            raise ValueError("route edge IDs must be unique")
        self._edges = {edge.edge_id: edge for edge in items}
        self.ledger = ledger if ledger is not None else TravelLedger()

    def start(self, journey_id: str, owner_id: str, plan: RoutePlan, tick: int, *, routine_id: str | None = None) -> TravelJourney:
        if not isinstance(plan, RoutePlan) or plan.owner_id != owner_id or not plan.found:
            raise ValueError("a found route plan for the same owner is required")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        selected: list[str] = []
        for start, end in zip(plan.path, plan.path[1:]):
            candidates = [edge for edge in self._edges.values()
                          if (edge.start_location_id == start and edge.end_location_id == end)
                          or (edge.bidirectional and edge.start_location_id == end and edge.end_location_id == start)]
            if not candidates:
                raise ValueError(f"route plan segment has no matching edge: {start} -> {end}")
            selected.append(min(candidates, key=lambda edge: (edge.travel_cost, edge.edge_id)).edge_id)
        status = "arrived" if not selected else "travelling"
        journey = TravelJourney(journey_id, owner_id, plan.origin, plan.destination, plan.path,
                                tuple(selected), edge_index=len(selected) if not selected else 0,
                                status=status, started_tick=tick, arrived_tick=tick if not selected else None,
                                routine_id=routine_id)
        return self.ledger.add(journey)

    def _edge_ids_for_plan(self, plan: RoutePlan) -> tuple[str, ...]:
        selected = []
        for start, end in zip(plan.path, plan.path[1:]):
            candidates = [edge for edge in self._edges.values()
                          if (edge.start_location_id == start and edge.end_location_id == end)
                          or (edge.bidirectional and edge.start_location_id == end and edge.end_location_id == start)]
            if not candidates:
                raise ValueError(f"route plan segment has no matching edge: {start} -> {end}")
            selected.append(min(candidates, key=lambda edge: (edge.travel_cost, edge.edge_id)).edge_id)
        return tuple(selected)

    def advance(self, tick: int, budgets: Mapping[str, float], *,
                closed_edge_ids: Iterable[str] = (),
                time_multipliers: Mapping[str, float] | None = None,
                route_planner: PersonalRoutePlanner | None = None,
                replan_blocked: bool = False,
                avoidance_profiles_by_owner: Mapping[str, Iterable[object]] | None = None,
                events: WorldEventLedger | None = None) -> TravelTickResult:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(budgets, Mapping):
            raise TypeError("budgets must map owner IDs to time units")
        clean_budgets: dict[str, float] = {}
        for owner, budget in budgets.items():
            if not isinstance(owner, str) or not owner.strip() or isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
                raise ValueError("each owner needs a non-negative finite travel budget")
            clean_budgets[owner] = float(budget)
        closed = tuple(sorted(set(closed_edge_ids)))
        if any(edge_id not in self._edges for edge_id in closed):
            raise ValueError("closed_edge_ids contains an unknown edge")
        supplied = time_multipliers or {}
        multipliers: dict[str, float] = {}
        for edge_id, multiplier in supplied.items():
            if edge_id not in self._edges or isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)) or not math.isfinite(multiplier) or multiplier <= 0:
                raise ValueError("time multipliers must reference known edges and be finite and positive")
            multipliers[edge_id] = float(multiplier)
        if events is not None and not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(replan_blocked, bool):
            raise ValueError("replan_blocked must be a boolean")
        if route_planner is not None and not isinstance(route_planner, PersonalRoutePlanner):
            raise TypeError("route_planner must be a PersonalRoutePlanner or None")
        if replan_blocked and route_planner is None:
            raise ValueError("route_planner is required when replan_blocked is enabled")
        supplied_profiles = avoidance_profiles_by_owner or {}
        if not isinstance(supplied_profiles, Mapping):
            raise TypeError("avoidance_profiles_by_owner must map owner IDs to profile iterables")
        profile_map = {}
        for owner, values in supplied_profiles.items():
            if not isinstance(owner, str) or not owner.strip():
                raise ValueError("avoidance profile owners must be non-empty strings")
            profiles = tuple(values)
            if any(not isinstance(profile, RoutineAvoidanceProfile) or profile.owner_id != owner for profile in profiles):
                raise ValueError("avoidance profiles must be RoutineAvoidanceProfile values scoped to their mapping owner")
            profile_map[owner] = profiles
        profile_signature = tuple((owner, profile_map[owner]) for owner in sorted(profile_map))
        signature = _tick_signature(tick, clean_budgets, closed, tuple(sorted(multipliers.items())), replan_blocked, profile_signature)
        prior = self.ledger._ticks.get(tick)
        if prior:
            if prior[0] != signature:
                raise ValueError(f"conflicting travel tick replay: {tick}")
            result = prior[1]
            if events is not None:
                self._materialize_arrivals(result, events)
            return result
        if self.ledger._ticks and tick <= max(self.ledger._ticks):
            raise ValueError("new travel ticks must advance monotonically")
        updated: list[TravelJourney] = []
        arrivals: list[str] = []
        blocked: list[str] = []
        for journey in self.ledger.snapshot():
            if journey.status not in ("travelling", "blocked", "unreachable"):
                continue
            index, progress, elapsed = journey.edge_index, journey.edge_progress, journey.elapsed_cost
            status, arrived_tick = journey.status, journey.arrived_tick
            path, edge_ids = journey.path, journey.edge_ids
            if status in ("blocked", "unreachable") and replan_blocked and progress <= 1e-12:
                plan = route_planner.plan(
                    journey.owner_id, journey.current_location, journey.destination,
                    avoidance_profiles=profile_map.get(journey.owner_id, ()),
                    closed_edge_ids=closed,
                )
                if plan.found:
                    replacement_edges = self._edge_ids_for_plan(plan)
                    path = path[:index + 1] + plan.path[1:]
                    edge_ids = edge_ids[:index] + replacement_edges
                    status = "travelling"
                else:
                    status = "unreachable"
                    blocked.append(journey.journey_id)
                    updated.append(replace(journey, status=status))
                    continue
            elif status in ("blocked", "unreachable"):
                blocked.append(journey.journey_id)
                continue
            budget = clean_budgets.get(journey.owner_id, 0.0)
            while budget > 1e-12 and index < len(edge_ids):
                edge_id = edge_ids[index]
                if edge_id in closed:
                    status = "blocked"
                    blocked.append(journey.journey_id)
                    break
                edge = self._edges[edge_id]
                multiplier = multipliers.get(edge_id, 1.0)
                remaining_time = (float(edge.travel_cost) - progress) * multiplier
                used = min(budget, remaining_time)
                progress += used / multiplier
                elapsed += used
                budget -= used
                if progress + 1e-12 >= float(edge.travel_cost):
                    index += 1
                    progress = 0.0
                else:
                    break
            if index >= len(edge_ids):
                status, arrived_tick = "arrived", tick
                arrivals.append(journey.journey_id)
            elif status != "blocked":
                status = "travelling"
            updated.append(replace(journey, path=path, edge_ids=edge_ids, edge_index=index,
                                   edge_progress=progress, elapsed_cost=elapsed,
                                   status=status, arrived_tick=arrived_tick))
        result = TravelTickResult(tick, tuple(updated), tuple(sorted(arrivals)), tuple(sorted(blocked)))
        result = self.ledger._apply_tick(tick, signature, result)
        if events is not None:
            self._materialize_arrivals(result, events)
        return result

    def _materialize_arrivals(self, result: TravelTickResult, events: WorldEventLedger) -> None:
        for journey_id in result.arrivals:
            journey = self.ledger.get(journey_id)
            events.append(WorldEventLedger.make_event(
                f"travel-arrival:{journey_id}", result.tick, "npc_arrived",
                participants=(journey.owner_id,),
                attributes={"journey_id": journey_id, "origin": journey.origin,
                            "destination": journey.destination, "elapsed_cost": journey.elapsed_cost,
                            "routine_id": journey.routine_id},
            ))

    def reopen(self, journey_id: str) -> TravelJourney:
        journey = self.ledger.get(journey_id)
        if journey is None:
            raise KeyError(journey_id)
        if journey.status != "blocked":
            return journey
        reopened = replace(journey, status="travelling")
        self.ledger._journeys[journey_id] = reopened
        return reopened
