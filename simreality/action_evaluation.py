"""Evidence-grounded evaluation of NPC action outcomes.

Evaluations compare authored action effects and execution policies with immutable
terminal records and their authoritative journal events. Learning is a bounded,
read-only projection for future decisions; it never rewrites plans or records.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from .action_execution import ActionExecution, ActionExecutionLedger
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class NPCActionEvaluation:
    evaluation_id: str
    execution_id: str
    owner_id: str
    action_id: str
    status: str
    expected_added_facts: tuple[str, ...]
    observed_added_facts: tuple[str, ...]
    missing_effects: tuple[str, ...]
    unexpected_added_facts: tuple[str, ...]
    expected_deleted_facts: tuple[str, ...]
    observed_deleted_facts: tuple[str, ...]
    expected_resource_costs: tuple[tuple[str, float], ...]
    observed_resource_costs: tuple[tuple[str, float], ...]
    expected_duration_ticks: int
    observed_duration_ticks: int
    deviation_flags: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class ActionEvaluationSnapshot:
    payload_json: str

    def to_json(self) -> str:
        raw = json.loads(self.payload_json)
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError("unsupported action evaluation snapshot")
        if not isinstance(raw.get("evaluations"), list) or not isinstance(raw.get("learning"), dict):
            raise ValueError("invalid action evaluation snapshot")
        canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if canonical != self.payload_json:
            raise ValueError("action evaluation snapshot must be canonical JSON")
        return canonical

    @classmethod
    def from_json(cls, payload: str) -> "ActionEvaluationSnapshot":
        raw = json.loads(payload)
        result = cls(json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False))
        result.to_json()
        return result


class ActionPlanEvaluationLedger:
    """Append-only execution assessments plus bounded per-action reliability stats."""

    def __init__(self, executions: ActionExecutionLedger,
                 events: WorldEventLedger | None = None, *, learning_min_samples: int = 3,
                 learning_rate: float = 0.2) -> None:
        if not isinstance(executions, ActionExecutionLedger):
            raise TypeError("executions must be an ActionExecutionLedger")
        self.executions = executions
        self.events = events if events is not None else executions.events
        if self.events is not executions.events:
            raise ValueError("evaluation and execution must share one event journal")
        if isinstance(learning_min_samples, bool) or not isinstance(learning_min_samples, int) or learning_min_samples < 1:
            raise ValueError("learning_min_samples must be a positive integer")
        if isinstance(learning_rate, bool) or not isinstance(learning_rate, (int, float)) or not math.isfinite(learning_rate) or not 0 < learning_rate <= 1:
            raise ValueError("learning_rate must be in (0, 1]")
        self.learning_min_samples = learning_min_samples
        self.learning_rate = float(learning_rate)
        self._evaluations: dict[str, NPCActionEvaluation] = {}
        self._learning: dict[str, dict[str, float | int]] = {}

    @property
    def history(self) -> tuple[NPCActionEvaluation, ...]:
        return tuple(self._evaluations[key] for key in sorted(self._evaluations))

    def reliability(self, action_id: str) -> float | None:
        item = self._learning.get(action_id)
        if item is None or item["samples"] < self.learning_min_samples:
            return None
        return float(item["reliability"])

    def evaluate(self, execution_id: str) -> NPCActionEvaluation:
        record = self.executions.get(execution_id)
        if record is None:
            raise ValueError("only terminal action executions can be evaluated")
        existing = self._evaluations.get(execution_id)
        if existing is not None:
            return existing
        start_id = f"action-execution:{execution_id}:started"
        finish_id = record.event_id
        finish_event = self.events.get(finish_id)
        if finish_event.event_type != "npc_action_execution" or finish_event.participants != (record.owner_id,):
            raise ValueError("execution journal provenance is inconsistent")
        finish_attrs = dict(finish_event.attributes)
        if (finish_attrs.get("execution_id") != execution_id
                or finish_attrs.get("action_id") != record.action_id
                or finish_attrs.get("status") != record.status):
            raise ValueError("execution record does not match journal evidence")
        start_event = None
        try:
            start_event = self.events.get(start_id)
        except KeyError:
            # The legacy one-shot execute() path records a single terminal event.
            if finish_id != f"action-execution:{execution_id}":
                raise ValueError("multi-tick execution is missing its start event")
        if start_event is not None:
            start_attrs = dict(start_event.attributes)
            if (start_event.event_type != "npc_action_started"
                    or start_event.tick > record.tick
                    or start_event.participants != (record.owner_id,)
                    or start_attrs.get("execution_id") != execution_id
                    or start_attrs.get("action_id") != record.action_id):
                raise ValueError("execution start event is inconsistent")

        action = self.executions.planner.actions[record.action_id]
        policy = self.executions.policies.get(record.action_id)
        expected_costs = tuple(sorted(policy.resource_costs)) if policy else ()
        before, after = set(record.facts_before), set(record.facts_after)
        observed_added = tuple(sorted(after - before))
        observed_deleted = tuple(sorted(before - after))
        expected_added = tuple(sorted(action.add_effects)) if record.status == "completed" else ()
        expected_deleted = tuple(sorted(action.delete_effects)) if record.status == "completed" else ()
        missing = tuple(sorted(set(expected_added) - set(observed_added)))
        unexpected = tuple(sorted(set(observed_added) - set(expected_added)))
        before_resources, after_resources = dict(record.resources_before), dict(record.resources_after)
        observed_costs = tuple(sorted(
            (key, max(0.0, value - after_resources.get(key, 0.0)))
            for key, value in before_resources.items()
            if value - after_resources.get(key, 0.0) > 1e-12
        ))
        expected_duration = (policy.duration_ticks if policy and start_event is not None else 1)
        observed_duration = (record.tick - start_event.tick if start_event is not None else 1)
        flags = []
        if record.status != "completed":
            flags.append(record.status)
        if missing:
            flags.append("expected_effect_absent")
        if unexpected:
            flags.append("unexpected_side_effect")
        if observed_costs != expected_costs:
            flags.append("resource_variance")
        if observed_duration != expected_duration:
            flags.append("duration_variance")
        evidence = ((finish_id,) if start_event is None else tuple(
            event.event_id for event in self.events.query(
                start_tick=start_event.tick, end_tick=record.tick,
                participant_id=record.owner_id,
            ) if dict(event.attributes).get("execution_id") == execution_id
        ))
        if finish_id not in evidence or (start_event is not None and start_id not in evidence):
            raise ValueError("execution evidence range is incomplete")
        evaluation_id = f"action-evaluation:{execution_id}"
        result = NPCActionEvaluation(
            evaluation_id, execution_id, record.owner_id, record.action_id,
            record.status, expected_added, observed_added, missing, unexpected,
            expected_deleted, observed_deleted, expected_costs, observed_costs,
            expected_duration, observed_duration, tuple(sorted(set(flags))),
            evidence, 1.0,
        )
        event_id = evaluation_id
        self.events.append(WorldEventLedger.make_event(
            event_id, record.tick, "npc_action_evaluated",
            participants=(record.owner_id,),
            attributes={"execution_id": execution_id, "action_id": record.action_id,
                        "status": record.status, "deviation_count": len(result.deviation_flags)},
        ))
        self._evaluations[execution_id] = result
        self._update_learning(result)
        return result

    def _update_learning(self, result: NPCActionEvaluation) -> None:
        state = self._learning.setdefault(result.action_id, {"samples": 0, "reliability": 0.5})
        observed_success = 1.0 if result.status == "completed" and not result.missing_effects else 0.0
        samples = int(state["samples"]) + 1
        prior = float(state["reliability"])
        reliability = prior + self.learning_rate * (observed_success - prior)
        self._learning[result.action_id] = {"samples": samples, "reliability": reliability}

    def to_snapshot(self) -> ActionEvaluationSnapshot:
        evaluations = []
        for item in self.history:
            data = {key: getattr(item, key) for key in item.__dataclass_fields__}
            data["expected_resource_costs"] = [list(x) for x in item.expected_resource_costs]
            data["observed_resource_costs"] = [list(x) for x in item.observed_resource_costs]
            for key in ("expected_added_facts", "observed_added_facts", "missing_effects",
                        "unexpected_added_facts", "expected_deleted_facts",
                        "observed_deleted_facts", "deviation_flags", "evidence_event_ids"):
                data[key] = list(data[key])
            evaluations.append(data)
        payload = {"schema_version": 1, "learning_min_samples": self.learning_min_samples,
                   "learning_rate": self.learning_rate, "evaluations": evaluations,
                   "learning": self._learning}
        return ActionEvaluationSnapshot(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))

    def restore_snapshot(self, snapshot: ActionEvaluationSnapshot) -> None:
        raw = json.loads(snapshot.to_json())
        if raw["learning_min_samples"] != self.learning_min_samples or raw["learning_rate"] != self.learning_rate:
            raise ValueError("evaluation learning configuration mismatch")
        restored = {}
        for data in raw["evaluations"]:
            execution_id = data["execution_id"]
            if execution_id in restored:
                raise ValueError("duplicate action evaluation")
            record = self.executions.get(execution_id)
            if record is None or record.owner_id != data["owner_id"] or record.action_id != data["action_id"]:
                raise ValueError("evaluation references an unknown or mismatched execution")
            event = self.events.get(data["evaluation_id"])
            attrs = dict(event.attributes)
            if (event.event_type != "npc_action_evaluated" or event.tick != record.tick
                    or event.participants != (record.owner_id,)
                    or attrs.get("execution_id") != execution_id
                    or attrs.get("action_id") != record.action_id):
                raise ValueError("evaluation does not match authoritative event")
            values = dict(data)
            for key in ("expected_added_facts", "observed_added_facts", "missing_effects",
                        "unexpected_added_facts", "expected_deleted_facts",
                        "observed_deleted_facts", "deviation_flags", "evidence_event_ids"):
                values[key] = tuple(values[key])
            for key in ("expected_resource_costs", "observed_resource_costs"):
                values[key] = tuple((x[0], x[1]) for x in values[key])
            evaluation = NPCActionEvaluation(**values)
            for evidence_id in evaluation.evidence_event_ids:
                self.events.get(evidence_id)
            restored[execution_id] = evaluation
        learning = raw["learning"]
        if not isinstance(learning, dict):
            raise ValueError("invalid learning projection")
        for action_id, item in learning.items():
            if (action_id not in self.executions.planner.actions
                    or not isinstance(item, dict) or item.get("samples", -1) < 0
                    or not 0 <= item.get("reliability", -1) <= 1):
                raise ValueError("invalid action learning state")
        self._evaluations = restored
        self._learning = {key: dict(value) for key, value in learning.items()}

    @classmethod
    def from_snapshot(cls, executions: ActionExecutionLedger, events: WorldEventLedger,
                      snapshot: ActionEvaluationSnapshot) -> "ActionPlanEvaluationLedger":
        ledger = cls(executions, events,
                     learning_min_samples=json.loads(snapshot.to_json())["learning_min_samples"],
                     learning_rate=json.loads(snapshot.to_json())["learning_rate"])
        ledger.restore_snapshot(snapshot)
        return ledger
