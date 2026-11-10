"""Replay-safe, one-step execution of an NPC's previously approved symbolic plan.

Planning remains advisory. This module executes only an explicitly supplied plan,
rechecks live preconditions and resources, and applies one action per call.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable, Mapping

from .planning import DeterministicPlanner, PlanningAction
from .world_events import WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class ActionExecutionPolicy:
    action_id: str
    resource_costs: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("action_id must be non-empty")
        if not isinstance(self.resource_costs, tuple):
            raise ValueError("resource_costs must be a tuple")
        keys = [key for key, _ in self.resource_costs]
        if len(keys) != len(set(keys)):
            raise ValueError("resource cost keys must be unique")
        for key, amount in self.resource_costs:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("resource names must be non-empty")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("resource costs must be finite and non-negative")


@dataclass(frozen=True)
class ActionExecution:
    execution_id: str
    owner_id: str
    tick: int
    action_id: str
    status: str
    reason: str
    facts_before: tuple[str, ...]
    facts_after: tuple[str, ...]
    resources_before: tuple[tuple[str, float], ...]
    resources_after: tuple[tuple[str, float], ...]
    event_id: str


class ActionExecutionLedger:
    """Execute one planned action with live validation and conflict-safe replay."""

    def __init__(self, planner: DeterministicPlanner,
                 policies: Iterable[ActionExecutionPolicy] = (),
                 events: WorldEventLedger | None = None) -> None:
        if not isinstance(planner, DeterministicPlanner):
            raise TypeError("planner must be a DeterministicPlanner")
        items = tuple(policies)
        if any(not isinstance(p, ActionExecutionPolicy) for p in items):
            raise TypeError("policies must contain ActionExecutionPolicy values")
        if len({p.action_id for p in items}) != len(items):
            raise ValueError("action policy IDs must be unique")
        unknown = {p.action_id for p in items} - set(planner.actions)
        if unknown:
            raise ValueError(f"policy references unknown action: {sorted(unknown)[0]}")
        if events is not None and not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        self.planner = planner
        self.policies = {p.action_id: p for p in items}
        self.events = events if events is not None else WorldEventLedger()
        self._records: dict[str, tuple[str, ActionExecution]] = {}

    @staticmethod
    def _canonical_facts(values) -> frozenset[str]:
        facts = frozenset(values)
        if any(not isinstance(x, str) or not x.strip() for x in facts):
            raise ValueError("facts must contain non-empty strings")
        return facts

    @staticmethod
    def _canonical_resources(values: Mapping[str, float]) -> dict[str, float]:
        result = dict(values)
        for key, amount in result.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("resource names must be non-empty")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("resource balances must be finite and non-negative")
        return result

    def execute(self, execution_id: str, owner_id: str, tick: int,
                action_id: str, world_facts: set[str] | frozenset[str],
                resources: dict[str, float], *,
                interruption: str | None = None) -> ActionExecution:
        if not isinstance(execution_id, str) or not execution_id.strip():
            raise ValueError("execution_id must be non-empty")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if action_id not in self.planner.actions:
            raise ValueError(f"unknown action: {action_id}")
        if interruption is not None and (not isinstance(interruption, str) or not interruption.strip()):
            raise ValueError("interruption must be non-empty text or None")
        facts = self._canonical_facts(world_facts)
        balances = self._canonical_resources(resources)
        policy = self.policies.get(action_id, ActionExecutionPolicy(action_id))
        request = json.dumps({
            "owner": owner_id, "tick": tick, "action": action_id,
            "facts": sorted(facts), "resources": sorted(balances.items()),
            "interruption": interruption,
        }, sort_keys=True, separators=(",", ":"), allow_nan=False)
        previous = self._records.get(execution_id)
        if previous is not None:
            if previous[0] != request:
                raise ValueError(f"conflicting action execution ID: {execution_id}")
            return previous[1]

        action = self.planner.actions[action_id]
        facts_after = set(facts)
        resources_after = dict(balances)
        if interruption is not None:
            status, reason = "interrupted", interruption
        elif not action.preconditions <= facts:
            status, reason = "blocked", "live action preconditions are not satisfied"
        elif any(balances.get(name, 0.0) < cost
                 for name, cost in policy.resource_costs):
            status, reason = "blocked", "insufficient resources"
        else:
            status, reason = "completed", "action effects applied"
            facts_after.difference_update(action.delete_effects)
            facts_after.update(action.add_effects)
            for name, cost in policy.resource_costs:
                resources_after[name] = balances.get(name, 0.0) - cost

        event_id = f"action-execution:{execution_id}"
        event = WorldEventLedger.make_event(
            event_id, tick, "npc_action_execution", participants=(owner_id,),
            attributes={
                "execution_id": execution_id, "action_id": action_id,
                "status": status, "reason": reason,
            },
        )
        record = ActionExecution(
            execution_id, owner_id, tick, action_id, status, reason,
            tuple(sorted(facts)), tuple(sorted(facts_after)),
            tuple(sorted(balances.items())), tuple(sorted(resources_after.items())),
            event_id,
        )
        self.events.append(event)
        self._records[execution_id] = (request, record)
        if status == "completed":
            world_facts.clear()
            world_facts.update(facts_after)
            resources.clear()
            resources.update(resources_after)
        return record

    def get(self, execution_id: str) -> ActionExecution | None:
        item = self._records.get(execution_id)
        return None if item is None else item[1]

    def snapshot(self) -> tuple[ActionExecution, ...]:
        return tuple(self._records[key][1] for key in sorted(self._records))
