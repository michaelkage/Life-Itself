"""Deterministic replanning that reconnects NPC goals to executable actions.

The coordinator is explicit: callers request a replan after changed facts,
priorities, resource constraints, or interruptions. It preserves the existing
execution ledger and world-event history rather than replacing either.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from .action_execution import ActionExecution, ActionExecutionLedger, ActiveActionExecution
from .action_evaluation import ActionPlanEvaluationLedger, NPCActionEvaluation, NPCPlanEvaluation
from .npc_autonomy import NPCDecision, NPCDecisionCycle
from .goal_arbitration import GoalCommitment
from .npc_life_history import NPCLifeHistory
from .npc_experience_transfer import (NPCExperienceTransferLedger, experience_action_guidance,
                                     strategic_experience_evidence, experience_goal_guidance)
from .planning import PlanResult
from .world_events import WorldEventLedger



@dataclass(frozen=True)
class NPCReplanningSnapshot:
    """Canonical, versioned idempotency history for autonomous replanning."""
    payload_json: str

    def to_json(self) -> str:
        raw = json.loads(self.payload_json)
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("requests"), list):
            raise ValueError("invalid NPC replanning snapshot")
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload_json:
            raise ValueError("NPC replanning snapshot must be canonical JSON")
        return canonical

    @classmethod
    def from_json(cls, payload: str) -> "NPCReplanningSnapshot":
        raw = json.loads(payload)
        snapshot = cls(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False))
        snapshot.to_json()
        return snapshot


@dataclass(frozen=True)
class NPCActionProgression:
    execution: ActionExecution | ActiveActionExecution
    next_active: ActiveActionExecution | None
    replanning: NPCReplanningResult | None
    evaluation: NPCActionEvaluation | None = None
    plan_evaluation: NPCPlanEvaluation | None = None


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
                 events: WorldEventLedger | None = None,
                 evaluations: ActionPlanEvaluationLedger | None = None,
                 life_history: NPCLifeHistory | None = None,
                 experience_transfers: NPCExperienceTransferLedger | None = None) -> None:
        if not isinstance(decisions, NPCDecisionCycle):
            raise TypeError("decisions must be an NPCDecisionCycle")
        if not isinstance(executions, ActionExecutionLedger):
            raise TypeError("executions must be an ActionExecutionLedger")
        self.decisions = decisions
        self.executions = executions
        self.events = events if events is not None else executions.events
        if self.events is not executions.events:
            raise ValueError("replanning and execution must share one event journal")
        if evaluations is not None and (evaluations.executions is not executions or evaluations.events is not self.events):
            raise ValueError("evaluation ledger must share the coordinator execution ledger and event journal")
        self.evaluations = evaluations
        if (life_history is None) != (experience_transfers is None):
            raise ValueError("life_history and experience_transfers must be supplied together")
        if experience_transfers is not None and experience_transfers.history is not life_history:
            raise ValueError("experience transfers must share the supplied life history")
        if experience_transfers is not None and experience_transfers.events is not self.events:
            raise ValueError("experience transfers must share the coordinator event journal")
        self.life_history = life_history
        self.experience_transfers = experience_transfers
        self._requests: dict[str, tuple[str, NPCReplanningResult]] = {}

    def to_snapshot(self) -> NPCReplanningSnapshot:
        requests = []
        for request_id, (signature, result) in sorted(self._requests.items()):
            decision = result.decision
            plan = None if decision.plan is None else {
                "success": decision.plan.success, "actions": list(decision.plan.actions),
                "total_cost": decision.plan.total_cost,
                "expanded_states": decision.plan.expanded_states,
                "reason": decision.plan.reason,
            }
            requests.append({
                "request_id": request_id, "signature": signature,
                "owner_id": result.owner_id, "tick": result.tick,
                "reason": result.reason, "goal_id": decision.goal_id,
                "goal_category": decision.goal_category, "decision_reason": decision.reason,
                "experience_evidence_ids": list(decision.experience_evidence_ids),
                "experience_evidence_sources": [list(x) for x in decision.experience_evidence_sources],
                "plan": plan, "status": result.status,
                "execution_id": result.execution_id, "action_id": result.action_id,
                "rejected_reason": result.rejected_reason, "event_id": result.event_id,
            })
        payload = {"schema_version": 1, "requests": requests}
        return NPCReplanningSnapshot(json.dumps(payload, sort_keys=True,
                                                  separators=(",", ":"), allow_nan=False))

    def restore_snapshot(self, snapshot: NPCReplanningSnapshot) -> None:
        if not isinstance(snapshot, NPCReplanningSnapshot):
            raise TypeError("snapshot must be an NPCReplanningSnapshot")
        raw = json.loads(snapshot.to_json())
        restored = {}
        for item in raw["requests"]:
            signature = item["signature"]
            request_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
            if request_id != item["request_id"] or request_id in restored:
                raise ValueError("replanning request identity is invalid or duplicated")
            request_data = json.loads(signature)
            if (request_data.get("owner") != item["owner_id"]
                    or request_data.get("tick") != item["tick"]
                    or (request_data.get("goal_commitment_id") is not None
                        and request_data.get("committed_goal_id") != item["goal_id"])
                    or request_data.get("experience_evidence_ids", []) != item.get("experience_evidence_ids", [])
                    or request_data.get("experience_evidence_sources", []) != item.get("experience_evidence_sources", [])):
                raise ValueError("replanning request metadata does not match its signature")
            event = self.events.get(item["event_id"])
            attributes = dict(event.attributes)
            if (event.event_type != "npc_action_replanned" or event.tick != item["tick"]
                    or item["owner_id"] not in event.participants
                    or attributes.get("request_id") != request_id
                    or attributes.get("status") != item["status"]
                    or attributes.get("action_id", "") != (item["action_id"] or "")
                    or attributes.get("goal_id", "") != (item["goal_id"] or "")
                    or attributes.get("reason") != item["reason"]
                    or attributes.get("experience_evidence_ids", "[]") != json.dumps(item.get("experience_evidence_ids", []), separators=(",", ":"))
                    or attributes.get("experience_evidence_sources", "[]") != json.dumps(item.get("experience_evidence_sources", []), separators=(",", ":"))):
                raise ValueError("replanning history does not match its world event")
            plan_data = item["plan"]
            plan = None if plan_data is None else PlanResult(
                plan_data["success"], tuple(plan_data["actions"]), plan_data["total_cost"],
                plan_data["expanded_states"], plan_data["reason"],
            )
            decision = NPCDecision(
                item["owner_id"], item["tick"], item["goal_id"],
                item["goal_category"], plan, item["decision_reason"],
                tuple(item.get("experience_evidence_ids", ())),
                tuple(tuple(x) for x in item.get("experience_evidence_sources", ())),
            )
            result = NPCReplanningResult(
                request_id, item["owner_id"], item["tick"], item["reason"], decision,
                item["status"], item["execution_id"], item["action_id"],
                item["rejected_reason"], item["event_id"],
            )
            restored[request_id] = (signature, result)
        self._requests = restored

    @classmethod
    def from_snapshot(cls, decisions: NPCDecisionCycle,
                      executions: ActionExecutionLedger,
                      events: WorldEventLedger,
                      snapshot: NPCReplanningSnapshot,
                      evaluations: ActionPlanEvaluationLedger | None = None,
                      life_history: NPCLifeHistory | None = None,
                      experience_transfers: NPCExperienceTransferLedger | None = None) -> "NPCActionReplanningCoordinator":
        coordinator = cls(decisions, executions, events, evaluations, life_history, experience_transfers)
        coordinator.restore_snapshot(snapshot)
        return coordinator

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
               max_expansions: int = 10_000,
               goal_motivational_adjustments: dict[str, float] | None = None,
               goal_commitment: GoalCommitment | None = None) -> NPCReplanningResult:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(world_facts, set) or not isinstance(resources, dict):
            raise TypeError("world_facts and resources must be mutable set/dict values")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be non-empty")
        if goal_commitment is not None:
            if not isinstance(goal_commitment, GoalCommitment):
                raise TypeError("goal_commitment must be GoalCommitment")
            if goal_commitment.owner_id != owner_id or goal_commitment.tick != tick:
                raise ValueError("goal commitment owner and tick must match the replan request")
        facts = sorted(self.executions._canonical_facts(world_facts))
        balances = sorted(self.executions._canonical_resources(resources).items())
        action_reliability = {}
        if self.evaluations is not None:
            action_reliability = {
                action_id: reliability
                for action_id in sorted(self.decisions.planner.actions)
                if (reliability := self.evaluations.reliability(action_id)) is not None
            }
        plan_reliability = (self.evaluations.plan_reliabilities()
                            if self.evaluations is not None else {})
        experience_ids: set[str] = set()
        experience_sources: dict[str, str] = {}
        goal_adjustments = {}
        goal_evidence_ids = {}
        if self.experience_transfers is not None:
            goal_adjustments, goal_evidence_ids, goal_sources = experience_goal_guidance(
                self.life_history, self.experience_transfers, owner_id, tick,
                self.decisions.goals)
            experience_reliability, evidence_by_action = experience_action_guidance(
                self.life_history, self.experience_transfers, owner_id, tick,
                self.decisions.planner.actions)
            experience_sources = {item.evidence_id: item.source_class for item in strategic_experience_evidence(
                self.life_history, self.experience_transfers, owner_id, tick)}
            for action_id, value in experience_reliability.items():
                prior = action_reliability.get(action_id)
                action_reliability[action_id] = value if prior is None else 0.75 * prior + 0.25 * value
                experience_ids.update(evidence_by_action[action_id])
            for ids in goal_evidence_ids.values():
                experience_ids.update(ids)
            experience_sources.update(goal_sources)
        request = {
            "owner": owner_id, "tick": tick, "facts": facts, "resources": balances,
            "action_reliability": sorted(action_reliability.items()),
            "experience_evidence_ids": sorted(experience_ids),
            "goal_experience_adjustments": sorted(goal_adjustments.items()),
            "goal_experience_evidence_ids": sorted((key, list(value)) for key, value in goal_evidence_ids.items()),
            "goal_motivational_adjustments": sorted((goal_motivational_adjustments or {}).items()),
            "experience_evidence_sources": sorted((key, experience_sources[key]) for key in experience_ids),
            "plan_reliability": [[goal_id, list(actions), value]
                                 for (goal_id, actions), value in sorted(plan_reliability.items())],
            "goal_facts": {key: sorted(value) for key, value in sorted(goal_facts.items())},
            "reason": reason, "active_execution_id": active_execution_id,
            "max_expansions": max_expansions,
            "goal_commitment_id": goal_commitment.commitment_id if goal_commitment else None,
            "committed_goal_id": goal_commitment.selected_goal_id if goal_commitment else None,
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
                if self.evaluations is not None:
                    self.evaluations.evaluate(active_execution_id)
                    prior_plan_id = active_execution_id.rsplit(":step:", 1)[0]
                    if prior_plan_id in self.evaluations._plans:
                        self.evaluations.evaluate_plan(prior_plan_id, "replanned")

        decision = self.decisions.decide(
            owner_id, tick, set(facts), goal_facts,
            max_expansions=max_expansions,
            action_reliability=action_reliability,
            plan_reliability=plan_reliability,
            goal_experience_adjustments=goal_adjustments,
            goal_motivational_adjustments=goal_motivational_adjustments,
            committed_goal_id=(goal_commitment.selected_goal_id if goal_commitment else None),
        )
        if experience_ids:
            decision = NPCDecision(decision.owner_id, decision.tick, decision.goal_id,
                                   decision.goal_category, decision.plan, decision.reason,
                                   tuple(sorted(experience_ids)),
                                   tuple(sorted((key, experience_sources[key]) for key in experience_ids)))
        execution_id = None
        action_id = None
        rejected_reason = None
        plan_id = f"replan:{request_id[:24]}"
        if decision.plan is not None and self.evaluations is not None and decision.goal_id is not None:
            self.evaluations.register_plan(
                plan_id, owner_id, decision.goal_id, tuple(decision.plan.actions),
                set(goal_facts.get(decision.goal_id, set())),
            )
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
                "experience_evidence_ids": json.dumps(sorted(experience_ids), separators=(",", ":")),
                "experience_evidence_sources": json.dumps(sorted((key, experience_sources[key]) for key in experience_ids), separators=(",", ":")),
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
        evaluation = self.evaluations.evaluate(execution_id) if self.evaluations is not None else None
        if terminal_or_active.status != "completed":
            plan_evaluation = (self.evaluations.evaluate_plan(
                execution_id.rsplit(":step:", 1)[0], "failed"
            ) if self.evaluations is not None else None)
            replanning = self.replan(
                active.owner_id, tick, world_facts, resources, goal_facts,
                reason=terminal_or_active.reason,
                max_expansions=max_expansions,
            )
            return NPCActionProgression(terminal_or_active, None, replanning, evaluation, plan_evaluation)

        next_index = active.action_index + 1
        if next_index >= len(active.plan_actions):
            plan_evaluation = (self.evaluations.evaluate_plan(
                execution_id.rsplit(":step:", 1)[0], "completed"
            ) if self.evaluations is not None else None)
            return NPCActionProgression(terminal_or_active, None, None, evaluation, plan_evaluation)

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
                return NPCActionProgression(terminal_or_active, next_active, None, evaluation)
            except ValueError as exc:
                failure = str(exc)

        plan_evaluation = (self.evaluations.evaluate_plan(
            execution_id.rsplit(":step:", 1)[0], "replanned"
        ) if self.evaluations is not None else None)
        replanning = self.replan(
            active.owner_id, tick, world_facts, resources, goal_facts,
            reason=f"remaining plan is no longer feasible: {failure}",
            max_expansions=max_expansions,
        )
        return NPCActionProgression(terminal_or_active, None, replanning, evaluation, plan_evaluation)
