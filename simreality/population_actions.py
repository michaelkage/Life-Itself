"""Validated bridge from NPC decision proposals to action execution starts.

A decision remains advisory until the live owner facts and resource balances
are supplied here. Only the first planned step is started; later steps require
fresh decisions or an explicit continuation policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .action_execution import ActionExecutionLedger, ActiveActionExecution
from .npc_autonomy import NPCDecision


@dataclass(frozen=True)
class NPCActionDispatch:
    owner_id: str
    execution_id: str | None
    action_id: str | None
    status: str
    reason: str
    active: ActiveActionExecution | None = None


class NPCActionDispatchAdapter:
    """Revalidate decision step zero against live facts/resources before start."""

    def __init__(self, executions: ActionExecutionLedger) -> None:
        if not isinstance(executions, ActionExecutionLedger):
            raise TypeError("executions must be an ActionExecutionLedger")
        self.executions = executions
        self._requests: dict[int, tuple[tuple, tuple[NPCActionDispatch, ...]]] = {}

    def dispatch(
        self,
        tick: int,
        decisions: tuple[NPCDecision, ...],
        world_facts_by_owner: Mapping[str, set[str]],
        resources_by_owner: Mapping[str, dict[str, float]],
        *,
        unavailable_owner_ids: frozenset[str] = frozenset(),
    ) -> tuple[NPCActionDispatch, ...]:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(decisions, tuple) or any(not isinstance(item, NPCDecision) for item in decisions):
            raise TypeError("decisions must be a tuple of NPCDecision values")
        if not isinstance(unavailable_owner_ids, frozenset) or any(
            not isinstance(owner, str) or not owner.strip() for owner in unavailable_owner_ids
        ):
            raise TypeError("unavailable_owner_ids must be a frozenset of non-empty owner IDs")
        if tuple(sorted(item.owner_id for item in decisions)) != tuple(item.owner_id for item in decisions):
            raise ValueError("decisions must be in stable owner-ID order")
        if len({item.owner_id for item in decisions}) != len(decisions):
            raise ValueError("at most one decision per NPC may be dispatched per tick")
        if not isinstance(world_facts_by_owner, Mapping) or not isinstance(resources_by_owner, Mapping):
            raise TypeError("owner facts and resources must be mappings")
        if set(world_facts_by_owner) != set(resources_by_owner):
            raise ValueError("world facts and resources must cover the same owners")
        for owner, facts in world_facts_by_owner.items():
            if not isinstance(owner, str) or not owner.strip() or not isinstance(facts, set):
                raise TypeError("owner facts must map non-empty IDs to mutable sets")
        for owner, resources in resources_by_owner.items():
            if not isinstance(owner, str) or not owner.strip() or not isinstance(resources, dict):
                raise TypeError("owner resources must map non-empty IDs to mutable dictionaries")
        signature = (
            tuple((d.owner_id, d.tick, d.goal_id, None if d.plan is None else (d.plan.success, d.plan.actions))
                  for d in decisions),
            tuple((owner, tuple(sorted(facts))) for owner, facts in sorted(world_facts_by_owner.items())),
            tuple((owner, tuple(sorted(values.items()))) for owner, values in sorted(resources_by_owner.items())),
            tuple(sorted(unavailable_owner_ids)),
        )
        prior = self._requests.get(tick)
        if prior is not None:
            if prior[0] != signature:
                raise ValueError(f"conflicting action dispatch replay: {tick}")
            return prior[1]

        output = []
        for decision in decisions:
            if decision.tick != tick:
                raise ValueError("decision tick must match dispatch tick")
            if not decision.actionable or not decision.plan.actions:
                output.append(NPCActionDispatch(
                    decision.owner_id, None, None, "not_dispatched",
                    decision.reason if not decision.actionable else "goal facts already satisfied",
                ))
                continue
            owner = decision.owner_id
            if owner in unavailable_owner_ids:
                output.append(NPCActionDispatch(
                    owner, None, None, "completed_this_tick",
                    "an action completed for this owner earlier in the population tick",
                ))
                continue
            active_for_owner = next((item for item in self.executions.active() if item.owner_id == owner), None)
            if active_for_owner is not None:
                replayed_start = active_for_owner.started_tick == tick
                output.append(NPCActionDispatch(
                    owner, active_for_owner.execution_id, active_for_owner.action_id,
                    "started" if replayed_start else "already_active",
                    "action start restored from this tick" if replayed_start else "owner already has an active action",
                    active_for_owner,
                ))
                continue
            if owner not in world_facts_by_owner or owner not in resources_by_owner:
                raise KeyError(f"missing live action state for NPC: {owner}")
            action_id = decision.plan.actions[0]
            execution_id = f"npc:{owner}:tick:{tick}:step:0"
            active = self.executions.start(
                execution_id, owner, tick, action_id,
                world_facts_by_owner[owner], resources_by_owner[owner],
                plan_actions=decision.plan.actions, action_index=0,
            )
            output.append(NPCActionDispatch(
                owner, execution_id, action_id, "started", "live preconditions and resources validated",
                active,
            ))
        result = tuple(output)
        self._requests[tick] = (signature, result)
        return result

    def advance_active(self, tick: int, world_state, *, owner_ids=None):
        """Advance active executions for the supplied owners in stable ID order."""
        from .action_world_state import ActionWorldState
        if not isinstance(world_state, ActionWorldState):
            raise TypeError("world_state must be an ActionWorldState")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if owner_ids is not None:
            if not isinstance(owner_ids, (tuple, list, set, frozenset)) or any(
                not isinstance(owner, str) or not owner.strip() for owner in owner_ids
            ):
                raise ValueError("owner_ids must contain non-empty owner IDs")
            selected = frozenset(owner_ids)
        else:
            selected = None
        results = []
        for active in self.executions.active():
            if selected is not None and active.owner_id not in selected:
                continue
            if active.last_tick >= tick:
                continue
            facts = world_state.world_facts_by_owner.get(active.owner_id)
            resources = world_state.resources_by_owner.get(active.owner_id)
            if facts is None or resources is None:
                raise KeyError(f"missing live action state for active owner: {active.owner_id}")
            results.append(self.executions.advance(active.execution_id, tick, facts, resources))
        return tuple(results)

    def discard_tick_cache(self, tick: int) -> None:
        """Discard derived dispatch output after a failed enclosing transaction."""
        self._requests.pop(tick, None)

    def snapshot(self) -> tuple[tuple[int, tuple[NPCActionDispatch, ...]], ...]:
        return tuple((tick, item[1]) for tick, item in sorted(self._requests.items()))
