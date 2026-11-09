"""Deterministic personal route selection with memory-derived location costs.

The route graph is explicit world state. Memory avoidance changes only the
requesting NPC's route costs; it never closes a road for other agents.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
from typing import Iterable

from .memory_routines import RoutineAvoidanceProfile


@dataclass(frozen=True)
class RouteEdge:
    edge_id: str
    start_location_id: str
    end_location_id: str
    travel_cost: float
    bidirectional: bool = True

    def __post_init__(self) -> None:
        for name in ("edge_id", "start_location_id", "end_location_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.start_location_id == self.end_location_id:
            raise ValueError("route edge must connect two different locations")
        if isinstance(self.travel_cost, bool) or not isinstance(self.travel_cost, (int, float)) or not math.isfinite(self.travel_cost) or self.travel_cost <= 0:
            raise ValueError("travel_cost must be finite and positive")
        if not isinstance(self.bidirectional, bool):
            raise ValueError("bidirectional must be a boolean")


@dataclass(frozen=True)
class RoutePlan:
    owner_id: str
    origin: str
    destination: str
    path: tuple[str, ...]
    base_cost: float
    adjusted_cost: float
    avoided_locations: tuple[str, ...]
    edge_ids: tuple[str, ...] = ()

    @property
    def found(self) -> bool:
        return bool(self.path)


class PersonalRoutePlanner:
    """Choose a stable lowest-cost path under one NPC's personal avoidance."""

    def __init__(self, edges: Iterable[RouteEdge]) -> None:
        items = tuple(edges)
        if any(not isinstance(edge, RouteEdge) for edge in items):
            raise TypeError("edges must contain RouteEdge values")
        ids = [edge.edge_id for edge in items]
        if len(ids) != len(set(ids)):
            raise ValueError("route edge IDs must be unique")
        self._adjacency: dict[str, list[tuple[str, float, str]]] = {}
        for edge in sorted(items, key=lambda item: item.edge_id):
            self._adjacency.setdefault(edge.start_location_id, []).append(
                (edge.end_location_id, float(edge.travel_cost), edge.edge_id)
            )
            if edge.bidirectional:
                self._adjacency.setdefault(edge.end_location_id, []).append(
                    (edge.start_location_id, float(edge.travel_cost), edge.edge_id)
                )
        for neighbours in self._adjacency.values():
            neighbours.sort(key=lambda item: (item[0], item[2]))

    def plan(
        self,
        owner_id: str,
        origin: str,
        destination: str,
        *,
        avoidance_profiles: Iterable[RoutineAvoidanceProfile] = (),
        avoidance_penalty_scale: float = 4.0,
        closed_edge_ids: Iterable[str] = (),
    ) -> RoutePlan:
        for name, value in (("owner_id", owner_id), ("origin", origin), ("destination", destination)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(avoidance_penalty_scale, bool) or not isinstance(avoidance_penalty_scale, (int, float)) or not math.isfinite(avoidance_penalty_scale) or avoidance_penalty_scale < 0:
            raise ValueError("avoidance_penalty_scale must be finite and non-negative")
        closed = frozenset(closed_edge_ids)
        known_edges = {item[2] for neighbours in self._adjacency.values() for item in neighbours}
        if any(not isinstance(edge_id, str) or not edge_id.strip() for edge_id in closed):
            raise ValueError("closed_edge_ids must contain non-empty edge IDs")
        if not closed.issubset(known_edges):
            raise ValueError("closed_edge_ids contains an unknown route edge")
        profiles = tuple(avoidance_profiles)
        if any(not isinstance(item, RoutineAvoidanceProfile) for item in profiles):
            raise TypeError("avoidance_profiles must contain RoutineAvoidanceProfile values")
        strengths: dict[str, float] = {}
        for profile in profiles:
            if profile.owner_id != owner_id:
                continue
            strengths[profile.location_id] = max(strengths.get(profile.location_id, 0.0), profile.strength)

        if origin == destination:
            return RoutePlan(owner_id, origin, destination, (origin,), 0.0, 0.0, (), ())
        # Heap ordering by (adjusted cost, complete path) makes equal-cost
        # choices stable and independent of edge insertion order.
        queue: list[tuple[float, tuple[str, ...], float, tuple[str, ...], tuple[str, ...]]] = [
            (0.0, (origin,), 0.0, (), ())
        ]
        best: dict[str, tuple[float, tuple[str, ...]]] = {origin: (0.0, (origin,))}
        while queue:
            adjusted, path, base, avoided, edge_path = heapq.heappop(queue)
            node = path[-1]
            if best.get(node) != (adjusted, path):
                continue
            if node == destination:
                return RoutePlan(owner_id, origin, destination, path, base, adjusted, avoided, edge_path)
            for neighbour, edge_cost, edge_id in self._adjacency.get(node, ()):
                if edge_id in closed or neighbour in path:
                    continue
                strength = strengths.get(neighbour, 0.0)
                penalty = edge_cost * float(avoidance_penalty_scale) * strength
                next_adjusted = adjusted + edge_cost + penalty
                next_path = path + (neighbour,)
                candidate = (next_adjusted, next_path)
                if neighbour not in best or candidate < best[neighbour]:
                    best[neighbour] = candidate
                    next_avoided = avoided + ((neighbour,) if strength > 0 else ())
                    next_edge_path = edge_path + (edge_id,)
                    heapq.heappush(queue, (next_adjusted, next_path, base + edge_cost, next_avoided, next_edge_path))
        return RoutePlan(owner_id, origin, destination, (), math.inf, math.inf, (), ())
