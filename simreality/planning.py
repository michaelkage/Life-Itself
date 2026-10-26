"""Deterministic, bounded symbolic planning for engine-independent NPC behavior.

The planner searches over explicit world facts and declared action effects. It does
not execute actions, invent missing world state, or use random choices. Callers
must validate and apply a returned plan against the live simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math


@dataclass(frozen=True)
class PlanningAction:
    action_id: str
    preconditions: frozenset[str]
    add_effects: frozenset[str]
    delete_effects: frozenset[str] = frozenset()
    cost: int = 1

    def validate(self) -> None:
        if not self.action_id.strip():
            raise ValueError("action_id must be non-empty")
        if isinstance(self.cost, bool) or not isinstance(self.cost, int) or self.cost <= 0:
            raise ValueError("action cost must be a positive integer")
        if self.add_effects & self.delete_effects:
            raise ValueError("an action cannot add and delete the same fact")
        if any(not isinstance(fact, str) or not fact.strip()
               for group in (self.preconditions, self.add_effects, self.delete_effects)
               for fact in group):
            raise ValueError("action facts must be non-empty strings")


@dataclass(frozen=True)
class PlanResult:
    success: bool
    actions: tuple[str, ...]
    total_cost: int
    expanded_states: int
    reason: str


class DeterministicPlanner:
    """Find a least-cost plan using stable tie-breaking and an expansion budget."""

    def __init__(self, actions: tuple[PlanningAction, ...] | list[PlanningAction]) -> None:
        self.actions: dict[str, PlanningAction] = {}
        for action in actions:
            action.validate()
            if action.action_id in self.actions:
                raise ValueError(f"duplicate action id: {action.action_id}")
            self.actions[action.action_id] = action
        self._ordered_actions = tuple(self.actions[key] for key in sorted(self.actions))

    @staticmethod
    def _facts(values: frozenset[str] | set[str] | tuple[str, ...]) -> frozenset[str]:
        result = frozenset(values)
        if any(not isinstance(fact, str) or not fact.strip() for fact in result):
            raise ValueError("world facts must be non-empty strings")
        return result

    def plan(
        self,
        initial_facts: frozenset[str] | set[str] | tuple[str, ...],
        goal_facts: frozenset[str] | set[str] | tuple[str, ...],
        *,
        max_expansions: int = 10_000,
    ) -> PlanResult:
        start = self._facts(initial_facts)
        goals = self._facts(goal_facts)
        if isinstance(max_expansions, bool) or not isinstance(max_expansions, int) or max_expansions < 1:
            raise ValueError("max_expansions must be a positive integer")
        if goals <= start:
            return PlanResult(True, (), 0, 0, "goal facts already satisfied")

        # Heap ordering is fully explicit: cost, action-id sequence, canonical state.
        start_key = tuple(sorted(start))
        frontier: list[tuple[int, tuple[str, ...], tuple[str, ...], frozenset[str]]] = [
            (0, (), start_key, start)
        ]
        best: dict[frozenset[str], tuple[int, tuple[str, ...]]] = {start: (0, ())}
        expanded = 0

        while frontier and expanded < max_expansions:
            cost, path, _, state = heapq.heappop(frontier)
            if best.get(state) != (cost, path):
                continue
            if goals <= state:
                return PlanResult(True, path, cost, expanded, "plan found")
            expanded += 1

            for action in self._ordered_actions:
                if not action.preconditions <= state:
                    continue
                next_state = (state - action.delete_effects) | action.add_effects
                next_cost = cost + action.cost
                next_path = path + (action.action_id,)
                previous = best.get(next_state)
                candidate = (next_cost, next_path)
                if previous is not None and previous <= candidate:
                    continue
                best[next_state] = candidate
                heapq.heappush(
                    frontier,
                    (next_cost, next_path, tuple(sorted(next_state)), next_state),
                )

        if frontier:
            return PlanResult(False, (), 0, expanded, "expansion budget exhausted")
        return PlanResult(False, (), 0, expanded, "no valid plan found")
