"""Replay-safe NPC action execution with checkpoints and multi-tick recovery.

Planning remains advisory. Execution rechecks live preconditions, reserves resources
while work is active, applies effects only on completion, and records world events.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Iterable, Mapping

from .planning import DeterministicPlanner
from .world_events import WorldEvent, WorldEventLedger


@dataclass(frozen=True)
class ActionExecutionPolicy:
    action_id: str
    resource_costs: tuple[tuple[str, float], ...] = ()
    duration_ticks: int = 1
    goal_progress: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("action_id must be non-empty")
        if not isinstance(self.resource_costs, tuple):
            raise ValueError("resource_costs must be a tuple")
        if len({key for key, _ in self.resource_costs}) != len(self.resource_costs):
            raise ValueError("resource cost keys must be unique")
        for key, amount in self.resource_costs:
            if not isinstance(key, str) or not key.strip() or isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("resource costs must have non-empty names and finite non-negative values")
        if isinstance(self.duration_ticks, bool) or not isinstance(self.duration_ticks, int) or self.duration_ticks < 1:
            raise ValueError("duration_ticks must be a positive integer")
        if not isinstance(self.goal_progress, tuple) or len({key for key, _ in self.goal_progress}) != len(self.goal_progress):
            raise ValueError("goal_progress must be a tuple with unique goal IDs")
        for goal_id, amount in self.goal_progress:
            if not isinstance(goal_id, str) or not goal_id.strip() or isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
                raise ValueError("goal progress entries require non-empty IDs and positive finite increments")


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


@dataclass(frozen=True)
class ActiveActionExecution:
    execution_id: str
    owner_id: str
    action_id: str
    plan_actions: tuple[str, ...]
    action_index: int
    started_tick: int
    last_tick: int
    progress_ticks: int
    duration_ticks: int
    reserved_resources: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ActionExecutionSnapshot:
    """Canonical JSON snapshot of completed records and resumable active actions."""
    json_payload: str

    def to_json(self) -> str:
        return self.json_payload

    @classmethod
    def from_json(cls, payload: str) -> "ActionExecutionSnapshot":
        try:
            raw = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid action execution snapshot JSON") from exc
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("unsupported action execution snapshot schema")
        if not isinstance(raw.get("records"), list) or not isinstance(raw.get("active"), list):
            raise ValueError("action execution snapshot requires records and active lists")
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return cls(canonical)


class ActionExecutionLedger:
    """Execute planned actions with live validation, reservations, and replay safety."""

    def __init__(self, planner: DeterministicPlanner,
                 policies: Iterable[ActionExecutionPolicy] = (),
                 events: WorldEventLedger | None = None, goals=None) -> None:
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
        if goals is not None and not hasattr(goals, "update_progress"):
            raise TypeError("goals must provide update_progress")
        self.planner = planner
        self.policies = {p.action_id: p for p in items}
        self.events = events if events is not None else WorldEventLedger()
        self.goals = goals
        if goals is not None:
            missing_goals = {goal_id for policy in items for goal_id, _ in policy.goal_progress} - set(goals.goals)
            if missing_goals:
                raise ValueError(f"action policy references unknown goal: {sorted(missing_goals)[0]}")
        self._records: dict[str, tuple[str, ActionExecution]] = {}
        self._active: dict[str, ActiveActionExecution] = {}
        self._tick_requests: dict[str, dict[int, str]] = {}

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
            if not isinstance(key, str) or not key.strip() or isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
                raise ValueError("resource balances must have non-empty names and finite non-negative values")
        return result

    def _validate_plan(self, action_id, plan_actions, action_index):
        if action_id not in self.planner.actions:
            raise ValueError(f"unknown action: {action_id}")
        if not isinstance(plan_actions, tuple) or not plan_actions or any(item not in self.planner.actions for item in plan_actions):
            raise ValueError("plan_actions must be a non-empty tuple of known action IDs")
        if isinstance(action_index, bool) or not isinstance(action_index, int) or not 0 <= action_index < len(plan_actions):
            raise ValueError("action_index must identify an action in plan_actions")
        if plan_actions[action_index] != action_id:
            raise ValueError("action_id does not match the selected plan step")

    def _reserved(self, resource: str, except_execution: str | None = None) -> float:
        return sum(dict(item.reserved_resources).get(resource, 0.0)
                   for key, item in self._active.items() if key != except_execution)

    def start(self, execution_id: str, owner_id: str, tick: int, action_id: str,
              world_facts: set[str], resources: dict[str, float], *,
              plan_actions: tuple[str, ...], action_index: int = 0) -> ActiveActionExecution:
        if not isinstance(execution_id, str) or not execution_id.strip() or not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("execution_id and owner_id must be non-empty")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(world_facts, set) or not isinstance(resources, dict):
            raise TypeError("world_facts and resources must be mutable set/dict values")
        self._validate_plan(action_id, plan_actions, action_index)
        if execution_id in self._active or execution_id in self._records:
            existing = self._active.get(execution_id)
            if existing and (existing.owner_id, existing.action_id, existing.plan_actions, existing.action_index) == (owner_id, action_id, plan_actions, action_index):
                return existing
            raise ValueError(f"conflicting action execution ID: {execution_id}")
        facts = self._canonical_facts(world_facts)
        balances = self._canonical_resources(resources)
        action = self.planner.actions[action_id]
        if not action.preconditions <= facts:
            raise ValueError("action preconditions are not satisfied")
        policy = self.policies.get(action_id, ActionExecutionPolicy(action_id))
        for name, cost in policy.resource_costs:
            if balances.get(name, 0.0) - self._reserved(name) < cost:
                raise ValueError(f"insufficient unreserved resource: {name}")
        active = ActiveActionExecution(
            execution_id, owner_id, action_id, plan_actions, action_index,
            tick, tick, 0, policy.duration_ticks, tuple(sorted(policy.resource_costs)),
        )
        event = WorldEventLedger.make_event(
            f"action-execution:{execution_id}:started", tick, "npc_action_started",
            participants=(owner_id,), attributes={"execution_id": execution_id, "action_id": action_id, "duration_ticks": policy.duration_ticks},
        )
        self.events.append(event)
        self._active[execution_id] = active
        self._tick_requests[execution_id] = {}
        return active

    def advance(self, execution_id: str, tick: int, world_facts: set[str],
                resources: dict[str, float], *, interruption: str | None = None) -> ActionExecution | ActiveActionExecution:
        active = self._active.get(execution_id)
        if active is None:
            record = self.get(execution_id)
            if record is not None:
                return record
            raise KeyError(execution_id)
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < active.last_tick:
            raise ValueError("advance tick cannot precede the previous execution tick")
        if tick == active.last_tick:
            if active.progress_ticks > 0:
                return active
            raise ValueError("first advance tick must be greater than the start tick")
        if not isinstance(world_facts, set) or not isinstance(resources, dict):
            raise TypeError("world_facts and resources must be mutable set/dict values")
        if interruption is not None and (not isinstance(interruption, str) or not interruption.strip()):
            raise ValueError("interruption must be non-empty text or None")
        facts = self._canonical_facts(world_facts)
        balances = self._canonical_resources(resources)
        action = self.planner.actions[active.action_id]
        policy = self.policies.get(active.action_id, ActionExecutionPolicy(active.action_id))
        if interruption is None and not action.preconditions <= facts:
            interruption = "live preconditions changed during execution"
        progress = active.progress_ticks + 1
        if interruption is None and progress < active.duration_ticks:
            updated = ActiveActionExecution(
                active.execution_id, active.owner_id, active.action_id, active.plan_actions,
                active.action_index, active.started_tick, tick, progress,
                active.duration_ticks, active.reserved_resources,
            )
            self._active[execution_id] = updated
            event = WorldEventLedger.make_event(
                f"action-execution:{execution_id}:tick:{tick}", tick, "npc_action_progress",
                participants=(active.owner_id,), attributes={"execution_id": execution_id, "progress_ticks": progress, "duration_ticks": active.duration_ticks},
            )
            self.events.append(event)
            return updated

        status = "interrupted" if interruption is not None else "completed"
        reason = interruption or "action effects applied"
        facts_after = set(facts)
        resources_after = dict(balances)
        if status == "completed":
            facts_after.difference_update(action.delete_effects)
            facts_after.update(action.add_effects)
            for name, cost in active.reserved_resources:
                if balances.get(name, 0.0) < cost:
                    status, reason = "interrupted", f"reserved resource no longer available: {name}"
                    facts_after = set(facts)
                    resources_after = dict(balances)
                    break
                resources_after[name] = balances.get(name, 0.0) - cost
        event_id = f"action-execution:{execution_id}:finished"
        event = WorldEventLedger.make_event(
            event_id, tick, "npc_action_execution", participants=(active.owner_id,),
            attributes={"execution_id": execution_id, "action_id": active.action_id, "status": status, "reason": reason},
        )
        record = ActionExecution(
            execution_id, active.owner_id, tick, active.action_id, status, reason,
            tuple(sorted(facts)), tuple(sorted(facts_after)),
            tuple(sorted(balances.items())), tuple(sorted(resources_after.items())), event_id,
        )
        self.events.append(event)
        if status == "completed":
            world_facts.clear()
            world_facts.update(facts_after)
            resources.clear()
            resources.update(resources_after)
            if self.goals is not None:
                for goal_id, amount in policy.goal_progress:
                    goal = self.goals.goals[goal_id]
                    self.goals.update_progress(goal_id, min(1.0, goal.progress + amount))
        self._active.pop(execution_id)
        self._tick_requests.pop(execution_id, None)
        signature = json.dumps({"owner": active.owner_id, "action": active.action_id, "plan": active.plan_actions, "index": active.action_index, "started": active.started_tick}, sort_keys=True, separators=(",", ":"))
        self._records[execution_id] = (signature, record)
        return record

    def cancel(self, execution_id: str, tick: int, reason: str) -> ActionExecution:
        active = self._active.get(execution_id)
        if active is None:
            existing = self.get(execution_id)
            if existing is not None:
                return existing
            raise KeyError(execution_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("cancellation reason must be non-empty")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < active.last_tick:
            raise ValueError("cancellation tick cannot precede the previous execution tick")
        # Cancellation is finalized through advance, so the same release and event path applies.
        facts = set()
        # Cancellation does not require current facts/resources; no effects or costs are applied.
        event_id = f"action-execution:{execution_id}:finished"
        event = WorldEventLedger.make_event(event_id, tick, "npc_action_execution",
            participants=(active.owner_id,), attributes={"execution_id": execution_id, "action_id": active.action_id, "status": "cancelled", "reason": reason})
        empty = ActionExecution(execution_id, active.owner_id, tick, active.action_id, "cancelled", reason, (), (), (), (), event_id)
        self.events.append(event)
        self._active.pop(execution_id)
        self._tick_requests.pop(execution_id, None)
        signature = json.dumps({"owner": active.owner_id, "action": active.action_id, "plan": active.plan_actions, "index": active.action_index, "started": active.started_tick}, sort_keys=True, separators=(",", ":"))
        self._records[execution_id] = (signature, empty)
        return empty

    def execute(self, execution_id: str, owner_id: str, tick: int,
                action_id: str, world_facts: set[str], resources: dict[str, float], *,
                plan_actions: tuple[str, ...], action_index: int = 0,
                interruption: str | None = None) -> ActionExecution:
        """Compatibility one-shot path; duration_ticks policies should use start/advance."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(world_facts, set) or not isinstance(resources, dict):
            raise TypeError("world_facts and resources must be mutable set/dict values")
        self._validate_plan(action_id, plan_actions, action_index)
        facts = self._canonical_facts(world_facts)
        balances = self._canonical_resources(resources)
        request = json.dumps({"owner": owner_id, "tick": tick, "action": action_id, "facts": sorted(facts), "resources": sorted(balances.items()), "plan_actions": plan_actions, "action_index": action_index, "interruption": interruption}, sort_keys=True, separators=(",", ":"), allow_nan=False)
        previous = self._records.get(execution_id)
        if previous is not None:
            if previous[0] != request:
                raise ValueError(f"conflicting action execution ID: {execution_id}")
            return previous[1]
        action = self.planner.actions[action_id]
        policy = self.policies.get(action_id, ActionExecutionPolicy(action_id))
        facts_after, resources_after = set(facts), dict(balances)
        if interruption is not None:
            status, reason = "interrupted", interruption
        elif not action.preconditions <= facts:
            status, reason = "blocked", "live action preconditions are not satisfied"
        elif any(balances.get(name, 0.0) - self._reserved(name) < cost for name, cost in policy.resource_costs):
            status, reason = "blocked", "insufficient resources"
        else:
            status, reason = "completed", "action effects applied"
            facts_after.difference_update(action.delete_effects)
            facts_after.update(action.add_effects)
            for name, cost in policy.resource_costs:
                resources_after[name] = balances.get(name, 0.0) - cost
        event_id = f"action-execution:{execution_id}"
        self.events.append(WorldEventLedger.make_event(event_id, tick, "npc_action_execution", participants=(owner_id,), attributes={"execution_id": execution_id, "action_id": action_id, "status": status, "reason": reason}))
        record = ActionExecution(execution_id, owner_id, tick, action_id, status, reason, tuple(sorted(facts)), tuple(sorted(facts_after)), tuple(sorted(balances.items())), tuple(sorted(resources_after.items())), event_id)
        self._records[execution_id] = (request, record)
        if status == "completed":
            world_facts.clear(); world_facts.update(facts_after)
            resources.clear(); resources.update(resources_after)
            if self.goals is not None:
                for goal_id, amount in policy.goal_progress:
                    goal = self.goals.goals[goal_id]
                    self.goals.update_progress(goal_id, min(1.0, goal.progress + amount))
        return record

    def get(self, execution_id: str) -> ActionExecution | None:
        item = self._records.get(execution_id)
        return None if item is None else item[1]

    def active(self, execution_id: str | None = None):
        if execution_id is not None:
            return self._active.get(execution_id)
        return tuple(self._active[key] for key in sorted(self._active))

    def snapshot(self) -> tuple[ActionExecution, ...]:
        return tuple(self._records[key][1] for key in sorted(self._records))

    def to_snapshot(self) -> ActionExecutionSnapshot:
        records = []
        for key in sorted(self._records):
            signature, r = self._records[key]
            records.append({"signature": signature, "record": r.__dict__})
        active = [self._active[key].__dict__ for key in sorted(self._active)]
        payload = {"schema_version": 1, "records": records, "active": active}
        return ActionExecutionSnapshot(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def restore_snapshot(self, snapshot: ActionExecutionSnapshot) -> None:
        if not isinstance(snapshot, ActionExecutionSnapshot):
            raise TypeError("snapshot must be an ActionExecutionSnapshot")
        raw = json.loads(snapshot.to_json())
        records = {}
        for item in raw["records"]:
            record_data = dict(item["record"])
            for field in ("facts_before", "facts_after"):
                record_data[field] = tuple(record_data[field])
            for field in ("resources_before", "resources_after"):
                record_data[field] = tuple(tuple(pair) for pair in record_data[field])
            record = ActionExecution(**record_data)
            if record.action_id not in self.planner.actions:
                raise ValueError("snapshot references an unknown action")
            if self.events.get(record.event_id) is None:
                raise ValueError("snapshot execution record is missing its world event")
            if record.execution_id in records:
                raise ValueError("duplicate execution ID in snapshot")
            records[record.execution_id] = (item["signature"], record)
        active = {}
        for item in raw["active"]:
            item["plan_actions"] = tuple(item["plan_actions"])
            item["reserved_resources"] = tuple(tuple(pair) for pair in item["reserved_resources"])
            record = ActiveActionExecution(**item)
            self._validate_plan(record.action_id, record.plan_actions, record.action_index)
            if record.execution_id in records or record.execution_id in active:
                raise ValueError("duplicate execution ID in snapshot")
            policy = self.policies.get(record.action_id, ActionExecutionPolicy(record.action_id))
            if record.duration_ticks != policy.duration_ticks or record.reserved_resources != tuple(sorted(policy.resource_costs)):
                raise ValueError("active action policy differs from the saved execution")
            if record.progress_ticks < 0 or record.progress_ticks >= record.duration_ticks or record.last_tick < record.started_tick:
                raise ValueError("invalid active execution progress")
            if self.events.get(f"action-execution:{record.execution_id}:started") is None:
                raise ValueError("active execution is missing its start event")
            active[record.execution_id] = record
        self._records, self._active = records, active
        self._tick_requests = {key: {} for key in active}

    @classmethod
    def from_snapshot(cls, planner, policies, events, snapshot, goals=None):
        ledger = cls(planner, policies, events, goals)
        ledger.restore_snapshot(snapshot)
        return ledger

    def to_json(self) -> str:
        return self.to_snapshot().to_json()

    @classmethod
    def from_json(cls, planner, policies, events, payload, goals=None):
        return cls.from_snapshot(planner, policies, events, ActionExecutionSnapshot.from_json(payload), goals)
