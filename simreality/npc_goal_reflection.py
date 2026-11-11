"""Evidence-bounded reflection and counterfactual comparison for NPC plans."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import math
from .action_evaluation import NPCPlanEvaluation
from .planning import DeterministicPlanner, PlanResult
from .world_events import WorldEventLedger

_CAUSES = frozenset({"own_decision", "insufficient_resources", "another_npc", "changed_circumstances"})

def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite numeric")
    return float(value)

@dataclass(frozen=True)
class GoalReflectionAlternative:
    alternative_id: str
    excluded_action_ids: tuple[str, ...]
    def __post_init__(self):
        if not isinstance(self.alternative_id, str) or not self.alternative_id.strip():
            raise ValueError("alternative_id must be non-empty")
        if (not isinstance(self.excluded_action_ids, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.excluded_action_ids)
                or self.excluded_action_ids != tuple(sorted(set(self.excluded_action_ids)))):
            raise ValueError("excluded_action_ids must be unique, sorted, non-empty action IDs")

@dataclass(frozen=True)
class GoalReflectionRule:
    deviation_causes: tuple[tuple[str, str, float], ...] = ()
    event_type_causes: tuple[tuple[str, str, float], ...] = ()
    max_alternatives: int = 4
    def __post_init__(self):
        for field in ("deviation_causes", "event_type_causes"):
            entries = getattr(self, field)
            if not isinstance(entries, tuple):
                raise TypeError(f"{field} must be a tuple")
            keys = []
            for item in entries:
                if not isinstance(item, tuple) or len(item) != 3:
                    raise ValueError(f"{field} entries must be (exact_key, cause, weight)")
                key, cause, weight = item
                if not isinstance(key, str) or not key.strip() or cause not in _CAUSES:
                    raise ValueError("invalid causal evidence key or category")
                weight = _number(weight, "causal weight")
                if not 0.0 < weight <= 1.0:
                    raise ValueError("causal weights must be in (0, 1]")
                keys.append(key)
            if len(keys) != len(set(keys)) or entries != tuple(sorted(entries)):
                raise ValueError(f"{field} must be unique and sorted by exact key")
        if (isinstance(self.max_alternatives, bool) or not isinstance(self.max_alternatives, int)
                or not 0 <= self.max_alternatives <= 16):
            raise ValueError("max_alternatives must be in [0, 16]")

@dataclass(frozen=True)
class GoalCounterfactualPlan:
    alternative_id: str
    excluded_action_ids: tuple[str, ...]
    plan: PlanResult
    cost_delta: int | None

    def __post_init__(self):
        if not isinstance(self.alternative_id, str) or not self.alternative_id.strip():
            raise ValueError("alternative_id must be non-empty")
        if (not isinstance(self.excluded_action_ids, tuple)
                or self.excluded_action_ids != tuple(sorted(set(self.excluded_action_ids)))
                or any(not isinstance(x, str) or not x.strip() for x in self.excluded_action_ids)):
            raise ValueError("excluded_action_ids must be unique, sorted, non-empty strings")
        if not isinstance(self.plan, PlanResult):
            raise TypeError("plan must be PlanResult")
        if self.plan.success:
            if isinstance(self.cost_delta, bool) or not isinstance(self.cost_delta, int):
                raise ValueError("successful counterfactual plans require an integer cost_delta")
        elif self.cost_delta is not None:
            raise ValueError("unsuccessful counterfactual plans must not have a cost_delta")

@dataclass(frozen=True)
class GoalPlanReflection:
    owner_id: str
    goal_id: str
    plan_id: str
    evaluated_tick: int
    causes: tuple[tuple[str, float], ...]
    primary_cause: str
    evidence_event_ids: tuple[str, ...]
    counterfactuals: tuple[GoalCounterfactualPlan, ...]
    reflection_id: str

    def __post_init__(self):
        for name in ("owner_id", "goal_id", "plan_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty")
        if isinstance(self.evaluated_tick, bool) or not isinstance(self.evaluated_tick, int) or self.evaluated_tick < 0:
            raise ValueError("evaluated_tick must be non-negative")
        if not isinstance(self.causes, tuple) or self.causes != tuple(sorted(self.causes)):
            raise ValueError("causes must be a sorted tuple")
        cause_names = [item[0] for item in self.causes]
        if len(cause_names) != len(set(cause_names)):
            raise ValueError("causal categories must be unique")
        for cause, weight in self.causes:
            if cause not in _CAUSES or not 0.0 < _number(weight, "cause weight") <= 1.0:
                raise ValueError("invalid causal category or weight")
        expected_primary = (sorted(self.causes, key=lambda x: (-x[1], x[0]))[0][0]
                            if self.causes else "undetermined")
        if self.primary_cause != expected_primary:
            raise ValueError("primary_cause must match the highest weighted cause")
        if not isinstance(self.evidence_event_ids, tuple) or self.evidence_event_ids != tuple(sorted(set(self.evidence_event_ids))):
            raise ValueError("evidence_event_ids must be unique and sorted")
        if not isinstance(self.counterfactuals, tuple) or any(
            not isinstance(item, GoalCounterfactualPlan) for item in self.counterfactuals
        ):
            raise TypeError("counterfactuals must contain GoalCounterfactualPlan values")
        alternative_ids = [item.alternative_id for item in self.counterfactuals]
        if alternative_ids != sorted(set(alternative_ids)):
            raise ValueError("counterfactual alternatives must be unique and sorted")
        if (not isinstance(self.reflection_id, str) or len(self.reflection_id) != 64
                or any(ch not in "0123456789abcdef" for ch in self.reflection_id)):
            raise ValueError("reflection_id must be a SHA-256 hex digest")

class NPCGoalReflectiveReasoner:
    """Read-only causal appraisal and deterministic alternative-plan comparison."""
    @staticmethod
    def reflect(evaluation: NPCPlanEvaluation, events: WorldEventLedger,
                planner: DeterministicPlanner, initial_facts: set[str],
                goal_facts: set[str], *, current_tick: int,
                rule: GoalReflectionRule,
                alternatives: tuple[GoalReflectionAlternative, ...] = (),
                resource_shortfalls: tuple[tuple[str, float, float], ...] = (),
                max_expansions: int = 10_000) -> GoalPlanReflection:
        if not isinstance(evaluation, NPCPlanEvaluation):
            raise TypeError("evaluation must be NPCPlanEvaluation")
        if not isinstance(events, WorldEventLedger) or not isinstance(planner, DeterministicPlanner):
            raise TypeError("events and planner have invalid types")
        if not isinstance(rule, GoalReflectionRule):
            raise TypeError("rule must be GoalReflectionRule")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        if not isinstance(initial_facts, set) or not isinstance(goal_facts, set):
            raise TypeError("initial_facts and goal_facts must be sets")
        if any(not isinstance(x, str) or not x.strip() for x in initial_facts | goal_facts):
            raise ValueError("facts must be non-empty strings")
        if not isinstance(alternatives, tuple) or any(not isinstance(x, GoalReflectionAlternative) for x in alternatives):
            raise TypeError("alternatives must be a tuple of GoalReflectionAlternative values")
        if len({x.alternative_id for x in alternatives}) != len(alternatives):
            raise ValueError("alternative IDs must be unique")
        if len(alternatives) > rule.max_alternatives:
            raise ValueError("alternative count exceeds the authored rule limit")
        if not isinstance(resource_shortfalls, tuple):
            raise TypeError("resource_shortfalls must be a tuple")
        shortfalls = []
        for item in resource_shortfalls:
            if not isinstance(item, tuple) or len(item) != 3:
                raise ValueError("resource shortfalls must be (resource, required, available)")
            name, required, available = item
            if not isinstance(name, str) or not name.strip():
                raise ValueError("resource names must be non-empty")
            required, available = _number(required, "required resource"), _number(available, "available resource")
            if required <= available or available < 0:
                raise ValueError("a resource shortfall requires required > available >= 0")
            shortfalls.append((name, required, available))
        if (shortfalls != sorted(set(shortfalls))
                or len({item[0] for item in shortfalls}) != len(shortfalls)):
            raise ValueError("resource shortfalls must have unique resource names and canonical order")

        matched = {}
        deviation_map = {key: (cause, weight) for key, cause, weight in rule.deviation_causes}
        for flag in evaluation.deviation_flags:
            if flag in deviation_map:
                cause, weight = deviation_map[flag]
                matched[cause] = matched.get(cause, 0.0) + weight
        if shortfalls:
            matched["insufficient_resources"] = matched.get("insufficient_resources", 0.0) + min(
                1.0, sum((required - available) / max(required, 1e-12)
                         for _, required, available in shortfalls))
        evidence_events = []
        for event_id in evaluation.evidence_event_ids:
            try:
                event = events.get(event_id)
            except KeyError as exc:
                raise ValueError(f"plan evaluation references missing event: {event_id}") from exc
            if event.tick > current_tick:
                raise ValueError("reflection evidence cannot come from the future")
            evidence_events.append(event)
        event_map = {key: (cause, weight) for key, cause, weight in rule.event_type_causes}
        for event in evidence_events:
            mapped = event_map.get(event.event_type)
            if mapped is None:
                continue
            cause, weight = mapped
            if cause == "another_npc" and not any(p != evaluation.owner_id for p in event.participants):
                continue
            matched[cause] = matched.get(cause, 0.0) + weight
        causes = tuple(sorted((cause, min(1.0, weight)) for cause, weight in matched.items() if weight > 0))
        primary = sorted(causes, key=lambda x: (-x[1], x[0]))[0][0] if causes else "undetermined"

        baseline_cost = sum(planner.actions[a].cost for a in evaluation.planned_actions if a in planner.actions)
        counterfactuals = []
        for alternative in sorted(alternatives, key=lambda x: x.alternative_id):
            unknown = set(alternative.excluded_action_ids) - set(planner.actions)
            if unknown:
                raise ValueError(f"counterfactual excludes unknown action: {sorted(unknown)[0]}")
            excluded = set(alternative.excluded_action_ids)
            candidate_planner = DeterministicPlanner(tuple(
                planner.actions[action_id] for action_id in sorted(planner.actions) if action_id not in excluded))
            candidate = candidate_planner.plan(initial_facts, goal_facts, max_expansions=max_expansions)
            counterfactuals.append(GoalCounterfactualPlan(
                alternative.alternative_id, alternative.excluded_action_ids, candidate,
                candidate.total_cost - baseline_cost if candidate.success else None))
        evidence_ids = tuple(sorted(set(evaluation.evidence_event_ids)))
        payload = {
            "owner": evaluation.owner_id, "goal": evaluation.goal_id, "plan": evaluation.plan_id,
            "tick": current_tick, "status": evaluation.terminal_status,
            "actions": list(evaluation.planned_actions), "deviations": list(evaluation.deviation_flags),
            "causes": [list(x) for x in causes], "primary": primary, "events": list(evidence_ids),
            "event_content": [[e.event_id, e.tick, e.event_type, list(e.participants),
                               list(e.witnesses), [list(x) for x in e.attributes]] for e in evidence_events],
            "shortfalls": [list(x) for x in shortfalls],
            "alternatives": [[x.alternative_id, list(x.excluded_action_ids), x.plan.success,
                              list(x.plan.actions), x.plan.total_cost, x.plan.expanded_states,
                              x.plan.reason, x.cost_delta] for x in counterfactuals],
            "rule": {"deviations": [list(x) for x in rule.deviation_causes],
                     "events": [list(x) for x in rule.event_type_causes],
                     "max_alternatives": rule.max_alternatives},
            "initial": sorted(initial_facts), "goals": sorted(goal_facts),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        return GoalPlanReflection(evaluation.owner_id, evaluation.goal_id, evaluation.plan_id,
                                  current_tick, causes, primary, evidence_ids,
                                  tuple(counterfactuals), digest)
