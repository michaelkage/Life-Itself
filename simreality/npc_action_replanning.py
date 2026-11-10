"""Deterministic replanning that reconnects NPC goals to executable actions.

The coordinator is explicit: callers request a replan after changed facts,
priorities, resource constraints, or interruptions. It preserves the existing
execution ledger and world-event history rather than replacing either.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .action_execution import ActionExecutionLedger
from .npc_autonomy import NPCDecision, NPCDecisionCycle
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class NPCActionProgression:
    execution: object
    next_active: object | None
    replanning: NPCReplanningResult | None


@dataclass(frozen=True)
class NPCReplanningResult:
    request_id: str
    owner_id: str
    tick: int
    reason: str
    decision: NPCDecision
    status: str
    execution_id: str | None
    action_id: str | None
    rejected_reason: str | None
    event_id: str


class NPCActionReplanningCoordinator:
    """Replan from live state and optionally start the first feasible action.

    Resource costs are checked cumulatively across the proposed plan, including
    reservations held by other active executions in the shared ledger. The
    symbolic planner itself remains resource-agnostic; an infeasible selected
    plan is reported as blocked rather than silently inventing an alternative.
    """

    def __init__(self, decisions: NPCDecisionCycle,
                 executions: ActionExecutionLedger,
                 events: WorldEventLedger | None = None) -> None:
        if not isinstance(decisions, NPCDecisionCycle):
            raise TypeError("decisions must be an NPCDecisionCycle")
        if not isinstance(executions, ActionExecutionLedger):
            raise TypeError("executions must be an ActionExecutionLedger")
        self.decisions = decisions
        self.executions = executions
        self.events = events if events is not None else executions.events
        if self.events is not executions.events:
            raise ValueError("replanning and execution must share one event journal")
        self._requests: dict[str, tuple[str, NPCReplanningResult]] = {}

    def _resource_failure(self, actions: tuple[str, ...],
                          resources: dict[str, float]) -> str | None:
        available = dict(self.executions._canonical_resources(resources))
        for active in self.executions.active():
            for name, amount in active.reserved_resources:
                available[name] = available.get(name, 0.0) - amount
        for action_id in actions:
            policy = self.executions.policies.get(action_id)
            if policy is None:
                continue
            for name, amount in policy.resource_costs:
                if available.get(name, 0.0) + 1e-12 < amount:
                    return (f"plan requires {amount:g} {name}; only "
                            f"{max(0.0, available.get(name, 0.0)):g} is available")
                available[name] = available.get(name, 0.0) - amount
        return None

    def replan(self, owner_id: str, tick: int, world_facts: set[str],
               resources: dict[str, float], goal_facts, *, reason: str,
               active_execution_id: str | None = None,
               max_expansions: int = 10_000) -> NPCReplanningResult:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(world_facts, set) or not isinstance(resources, dict):
            raise TypeError("world_facts and resources must be mutable set/dict values")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be non-empty")
        facts = sorted(self.executions._canonical_facts(world_facts))
        balances = sorted(self.executions._canonical_resources(resources).items())
        request = {
            "owner": owner_id, "tick": tick, "facts": facts, "resources": balances,
            "goal_facts": {key: sorted(value) for key, value in sorted(goal_facts.items())},
            "reason": reason, "active_execution_id": active_execution_id,
            "max_expansions": max_expansions,
        }
        signature = json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)
        request_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        previous = self._requests.get(request_id)
        if previous is not None:
            if previous[0] != signature:
                raise ValueError("replanning request hash collision")
            return previous[1]

        if active_execution_id is not None:
            active = self.executions.active(active_execution_id)
            if active is not None:
                if active.owner_id != owner_id:
                    raise ValueError("active execution belongs to another NPC")
                self.executions.cancel(active_execution_id, tick, f"replan: {reason}")

        decision = self.decisions.decide(
            owner_id, tick, set(facts), goal_facts,
            max_expansions=max_expansions,
        )
        execution_id = None
        action_id = None
        rejected_reason = None
        if not decision.actionable:
            status = "unplanned"
            rejected_reason = decision.reason
        elif decision.plan.actions:
            rejected_reason = self._resource_failure(decision.plan.actions, resources)
            if rejected_reason is not None:
                status = "blocked"
            else:
                action_id = decision.plan.actions[0]
                execution_id = f"replan:{request_id[:24]}:step:0"
                self.executions.start(
                    execution_id, owner_id, tick, action_id, world_facts, resources,
                    plan_actions=decision.plan.actions, action_index=0,
                )
                status = "started"
        else:
            status = "already_satisfied"

        event_id = f"npc-replan:{request_id}"
        self.events.append(WorldEventLedger.make_event(
            event_id, tick, "npc_action_replanned", participants=(owner_id,),
            attributes={
                "request_id": request_id, "reason": reason, "goal_id": decision.goal_id or "",
                "status": status, "action_id": action_id or "",
                "rejected_reason": rejected_reason or "",
            },
        ))
        result = NPCReplanningResult(
            request_id, owner_id, tick, reason, decision, status,
            execution_id, action_id, rejected_reason, event_id,
        )
        self._requests[request_id] = (signature, result)
        return result

    def advance(self, execution_id: str, tick: int, world_facts: set[str],
                resources: dict[str, float], goal_facts, *,
                interruption: str | None = None,
                max_expansions: int = 10_000) -> NPCActionProgression:
        """Advance one action, continue its plan, or replan after failure.

        Each plan step receives its own stable execution ID. The prior action's
        terminal record remains in the ledger when the next step starts.
        """
        active = self.executions.active(execution_id)
        if active is None:
            raise KeyError(execution_id)
        terminal_or_active = self.executions.advance(
            execution_id, tick, world_facts, resources, interruption=interruption,
        )
        if not hasattr(terminal_or_active, "status"):
            return NPCActionProgression(terminal_or_active, terminal_or_active, None)
        if terminal_or_active.status != "completed":
            replanning = self.replan(
                active.owner_id, tick, world_facts, resources, goal_facts,
                reason=terminal_or_active.reason,
                max_expansions=max_expansions,
            )
            return NPCActionProgression(terminal_or_active, None, replanning)

        next_index = active.action_index + 1
        if next_index >= len(active.plan_actions):
            return NPCActionProgression(terminal_or_active, None, None)

        remaining = active.plan_actions[next_index:]
        failure = self._resource_failure(remaining, resources)
        next_id = f"{execution_id.rsplit(':step:', 1)[0]}:step:{next_index}"
        if failure is None:
            try:
                next_active = self.executions.start(
                    next_id, active.owner_id, tick, remaining[0],
                    world_facts, resources, plan_actions=active.plan_actions,
                    action_index=next_index,
                )
                return NPCActionProgression(terminal_or_active, next_active, None)
            except ValueError as exc:
                failure = str(exc)

        replanning = self.replan(
            active.owner_id, tick, world_facts, resources, goal_facts,
            reason=f"remaining plan is no longer feasible: {failure}",
            max_expansions=max_expansions,
        )
        return NPCActionProgression(terminal_or_active, None, replanning)
