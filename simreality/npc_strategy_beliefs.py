"""Owner-specific, evidence-bounded learning about strategy reliability.

Only terminal plan evaluations produce observations. Replanned work is neutral,
and counterfactual reflections are context, never fabricated outcomes. Strategy
belief changes require an explicit owner decision and remain append-only.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math


def _digest(payload):
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")).hexdigest()


def _unit(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return float(value)


def _nonempty(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class StrategyLearningRule:
    rule_id: str
    minimum_observations: int = 3
    prior_alpha: float = 1.0
    prior_beta: float = 1.0
    minimum_confidence_delta: float = 0.15

    def __post_init__(self):
        _nonempty(self.rule_id, "rule_id")
        if isinstance(self.minimum_observations, bool) or not isinstance(self.minimum_observations, int) or self.minimum_observations < 2:
            raise ValueError("minimum_observations must be an integer of at least 2")
        for name in ("prior_alpha", "prior_beta"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
            object.__setattr__(self, name, float(value))
        delta = _unit(self.minimum_confidence_delta, "minimum_confidence_delta")
        if delta <= 0 or delta >= 0.5:
            raise ValueError("minimum_confidence_delta must be in (0, 0.5)")
        object.__setattr__(self, "minimum_confidence_delta", delta)


@dataclass(frozen=True)
class StrategyObservation:
    observation_id: str
    owner_id: str
    goal_id: str
    strategy_id: str
    context_key: str
    plan_id: str
    action_sequence: tuple[str, ...]
    outcome: str
    confidence: float
    observed_tick: int
    evidence_event_ids: tuple[str, ...]
    reflection_id: str | None

    def __post_init__(self):
        for name in ("observation_id", "owner_id", "goal_id", "strategy_id", "context_key", "plan_id"):
            _nonempty(getattr(self, name), name)
        if (not isinstance(self.action_sequence, tuple) or not self.action_sequence
                or any(not isinstance(x, str) or not x.strip() for x in self.action_sequence)):
            raise ValueError("action_sequence must contain non-empty action IDs")
        if self.outcome not in ("success", "failure"):
            raise ValueError("strategy observations must be success or failure")
        _unit(self.confidence, "confidence")
        if isinstance(self.observed_tick, bool) or not isinstance(self.observed_tick, int) or self.observed_tick < 0:
            raise ValueError("observed_tick must be non-negative")
        if (not isinstance(self.evidence_event_ids, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.evidence_event_ids)
                or self.evidence_event_ids != tuple(sorted(set(self.evidence_event_ids)))):
            raise ValueError("evidence_event_ids must be unique, sorted, non-empty strings")
        if self.reflection_id is not None:
            _nonempty(self.reflection_id, "reflection_id")
            if len(self.reflection_id) != 64 or any(ch not in "0123456789abcdef" for ch in self.reflection_id):
                raise ValueError("reflection_id must be a SHA-256 hex digest")
        expected_strategy = _digest({"goal": self.goal_id, "actions": list(self.action_sequence)})
        if self.strategy_id != expected_strategy:
            raise ValueError("strategy_id does not match goal and ordered action sequence")
        expected = _digest({
            "owner": self.owner_id, "goal": self.goal_id, "strategy": self.strategy_id,
            "context": self.context_key, "plan": self.plan_id,
            "actions": list(self.action_sequence), "outcome": self.outcome,
            "confidence": self.confidence, "tick": self.observed_tick,
            "events": list(self.evidence_event_ids), "reflection": self.reflection_id,
        })
        if self.observation_id != expected:
            raise ValueError("observation_id does not match immutable observation content")

    @classmethod
    def from_evaluation(cls, evaluation, context_key, *, reflection=None, observed_tick=None):
        from .action_evaluation import NPCPlanEvaluation
        if not isinstance(evaluation, NPCPlanEvaluation):
            raise TypeError("evaluation must be NPCPlanEvaluation")
        _nonempty(context_key, "context_key")
        if evaluation.terminal_status == "replanned":
            return None
        if evaluation.terminal_status not in ("completed", "failed"):
            raise ValueError("unsupported terminal plan outcome")
        if reflection is not None:
            from .npc_goal_reflection import GoalPlanReflection
            if not isinstance(reflection, GoalPlanReflection):
                raise TypeError("reflection must be GoalPlanReflection")
            if (reflection.owner_id, reflection.goal_id, reflection.plan_id) != (
                evaluation.owner_id, evaluation.goal_id, evaluation.plan_id
            ):
                raise ValueError("reflection must reference the same owner, goal, and plan")
        tick = observed_tick
        if tick is None:
            # Plan evaluations do not carry a terminal tick. Require callers to
            # provide it rather than deriving chronology from an unrelated event.
            raise ValueError("observed_tick is required for strategy learning")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("observed_tick must be non-negative")
        if reflection is not None and reflection.evaluated_tick > tick:
            raise ValueError("reflection cannot postdate the strategy observation")
        outcome = ("success" if evaluation.terminal_status == "completed"
                   and not evaluation.missing_goal_facts else "failure")
        strategy_id = _digest({"goal": evaluation.goal_id, "actions": list(evaluation.planned_actions)})
        evidence = tuple(sorted(set(evaluation.evidence_event_ids)))
        confidence = _unit(evaluation.confidence, "evaluation confidence")
        if confidence == 0.0:
            return None
        reflection_id = reflection.reflection_id if reflection is not None else None
        payload = {
            "owner": evaluation.owner_id, "goal": evaluation.goal_id, "strategy": strategy_id,
            "context": context_key, "plan": evaluation.plan_id,
            "actions": list(evaluation.planned_actions), "outcome": outcome,
            "confidence": confidence, "tick": tick, "events": list(evidence),
            "reflection": reflection_id,
        }
        return cls(_digest(payload), evaluation.owner_id, evaluation.goal_id, strategy_id,
                   context_key, evaluation.plan_id, tuple(evaluation.planned_actions),
                   outcome, confidence, tick, evidence,
                   reflection_id)


@dataclass(frozen=True)
class StrategyBeliefProposal:
    proposal_id: str
    owner_id: str
    goal_id: str
    strategy_id: str
    context_key: str
    rule_id: str
    minimum_observations: int
    minimum_confidence_delta: float
    prior_alpha: float
    prior_beta: float
    observation_ids: tuple[str, ...]
    reflection_ids: tuple[str, ...]
    success_weight: float
    failure_weight: float
    posterior_confidence: float
    prior_confidence: float
    confidence_delta: float
    sample_count: int

    def __post_init__(self):
        for name in ("proposal_id", "owner_id", "goal_id", "strategy_id", "context_key", "rule_id"):
            _nonempty(getattr(self, name), name)
        if isinstance(self.minimum_observations, bool) or not isinstance(self.minimum_observations, int) or self.minimum_observations < 2:
            raise ValueError("minimum_observations must be at least 2")
        _unit(self.minimum_confidence_delta, "minimum_confidence_delta")
        if not 0 < self.minimum_confidence_delta < 0.5:
            raise ValueError("minimum_confidence_delta must be in (0, 0.5)")
        for name in ("prior_alpha", "prior_beta"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("success_weight", "failure_weight", "posterior_confidence", "prior_confidence"):
            _unit(getattr(self, name), name)
        if not isinstance(self.confidence_delta, (int, float)) or isinstance(self.confidence_delta, bool) or not math.isfinite(self.confidence_delta) or not -1 <= self.confidence_delta <= 1:
            raise ValueError("confidence_delta must be finite and in [-1, 1]")
        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int) or self.sample_count < 2:
            raise ValueError("sample_count must be at least 2")
        for name in ("observation_ids", "reflection_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or values != tuple(sorted(set(values))):
                raise ValueError(f"{name} must be unique and sorted")
        expected = _digest({
            "owner": self.owner_id, "goal": self.goal_id, "strategy": self.strategy_id,
            "context": self.context_key, "rule": self.rule_id,
            "minimum_observations": self.minimum_observations,
            "minimum_confidence_delta": self.minimum_confidence_delta,
            "prior_alpha": self.prior_alpha, "prior_beta": self.prior_beta,
            "observations": list(self.observation_ids), "reflections": list(self.reflection_ids),
            "success": self.success_weight, "failure": self.failure_weight,
            "posterior": self.posterior_confidence, "prior": self.prior_confidence,
            "delta": self.confidence_delta, "samples": self.sample_count,
        })
        if self.proposal_id != expected:
            raise ValueError("proposal_id does not match proposal content")


@dataclass(frozen=True)
class StrategyBeliefDecision:
    decision_id: str
    proposal_id: str
    rule_id: str
    owner_id: str
    goal_id: str
    strategy_id: str
    context_key: str
    accepted: bool
    decision_tick: int
    rationale: str
    confidence: float
    observation_ids: tuple[str, ...]
    minimum_observations: int
    minimum_confidence_delta: float
    prior_alpha: float
    prior_beta: float

    def __post_init__(self):
        for name in ("decision_id", "proposal_id", "rule_id", "owner_id", "goal_id", "strategy_id", "context_key", "rationale"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be bool")
        if isinstance(self.decision_tick, bool) or not isinstance(self.decision_tick, int) or self.decision_tick < 0:
            raise ValueError("decision_tick must be non-negative")
        _unit(self.confidence, "confidence")
        if (not isinstance(self.observation_ids, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.observation_ids)
                or self.observation_ids != tuple(sorted(set(self.observation_ids)))):
            raise ValueError("observation_ids must be unique, sorted, non-empty strings")
        expected = _digest({"proposal": self.proposal_id, "accepted": self.accepted,
                            "tick": self.decision_tick, "rationale": self.rationale})
        if self.decision_id != expected:
            raise ValueError("decision_id does not match immutable decision content")
        if isinstance(self.minimum_observations, bool) or not isinstance(self.minimum_observations, int) or self.minimum_observations < 2:
            raise ValueError("minimum_observations must be at least 2")
        _unit(self.minimum_confidence_delta, "minimum_confidence_delta")
        if not 0 < self.minimum_confidence_delta < 0.5:
            raise ValueError("minimum_confidence_delta must be in (0, 0.5)")
        for name in ("prior_alpha", "prior_beta"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class StrategyBelief:
    owner_id: str
    goal_id: str
    strategy_id: str
    context_key: str
    confidence: float
    decision_id: str
    updated_tick: int
    action_sequence: tuple[str, ...]


class NPCStrategyBeliefLedger:
    """Append-only observations and owner decisions; beliefs are accepted projections."""
    def __init__(self, observations=(), decisions=()):
        self._observations = {}
        self._decisions = {}
        self._proposal_decisions = {}
        for item in sorted(tuple(observations), key=lambda x: (x.observed_tick, x.observation_id)):
            self.record(item)
        for item in sorted(tuple(decisions), key=lambda x: (x.decision_tick, x.decision_id)):
            self._store_decision(item)

    def record(self, observation):
        if not isinstance(observation, StrategyObservation):
            raise TypeError("observation must be StrategyObservation")
        existing = self._observations.get(observation.observation_id)
        if existing is not None:
            if existing != observation:
                raise ValueError("observation ID reused with conflicting content")
            return existing
        if any(x.plan_id == observation.plan_id and x.owner_id == observation.owner_id
               for x in self._observations.values()):
            raise ValueError("a plan may produce only one strategy observation per owner")
        self._observations[observation.observation_id] = observation
        return observation

    def observe_evaluation(self, evaluation, context_key, *, reflection=None, observed_tick=None):
        observation = StrategyObservation.from_evaluation(
            evaluation, context_key, reflection=reflection, observed_tick=observed_tick)
        return self.record(observation) if observation is not None else None

    def observations(self):
        return tuple(sorted(self._observations.values(), key=lambda x: (x.observed_tick, x.observation_id)))

    def assess(self, owner_id, strategy_id, context_key, rule):
        _nonempty(owner_id, "owner_id")
        _nonempty(strategy_id, "strategy_id")
        _nonempty(context_key, "context_key")
        if not isinstance(rule, StrategyLearningRule):
            raise TypeError("rule must be StrategyLearningRule")
        items = tuple(x for x in self.observations()
                      if (x.owner_id, x.strategy_id, x.context_key) == (owner_id, strategy_id, context_key))
        if len(items) < rule.minimum_observations:
            return None
        success = sum(x.confidence for x in items if x.outcome == "success")
        failure = sum(x.confidence for x in items if x.outcome == "failure")
        prior = rule.prior_alpha / (rule.prior_alpha + rule.prior_beta)
        posterior = (rule.prior_alpha + success) / (rule.prior_alpha + rule.prior_beta + success + failure)
        delta = posterior - prior
        if abs(delta) < rule.minimum_confidence_delta:
            return None
        observation_ids = tuple(sorted(x.observation_id for x in items))
        reflection_ids = tuple(sorted({x.reflection_id for x in items if x.reflection_id is not None}))
        payload = {
            "owner": owner_id, "goal": items[0].goal_id, "strategy": strategy_id,
            "context": context_key, "rule": rule.rule_id,
            "observations": list(observation_ids), "reflections": list(reflection_ids),
            "minimum_observations": rule.minimum_observations,
            "minimum_confidence_delta": rule.minimum_confidence_delta,
            "prior_alpha": rule.prior_alpha, "prior_beta": rule.prior_beta,
            "success": success, "failure": failure, "posterior": posterior,
            "prior": prior, "delta": delta, "samples": len(items),
        }
        return StrategyBeliefProposal(_digest(payload), owner_id, items[0].goal_id,
            strategy_id, context_key, rule.rule_id, rule.minimum_observations,
            rule.minimum_confidence_delta, rule.prior_alpha, rule.prior_beta,
            observation_ids, reflection_ids, success, failure, posterior, prior, delta, len(items))

    def decide(self, proposal, *, accepted, decision_tick, rationale):
        if not isinstance(proposal, StrategyBeliefProposal):
            raise TypeError("proposal must be StrategyBeliefProposal")
        if not isinstance(accepted, bool):
            raise TypeError("accepted must be bool")
        if isinstance(decision_tick, bool) or not isinstance(decision_tick, int) or decision_tick < 0:
            raise ValueError("decision_tick must be non-negative")
        _nonempty(rationale, "rationale")
        known = {x.observation_id for x in self._observations.values()}
        if not set(proposal.observation_ids).issubset(known):
            raise ValueError("proposal references unknown strategy observations")
        items = [self._observations[x] for x in proposal.observation_ids]
        if any((x.owner_id, x.goal_id, x.strategy_id, x.context_key) !=
               (proposal.owner_id, proposal.goal_id, proposal.strategy_id, proposal.context_key)
               for x in items):
            raise ValueError("proposal evidence crosses owner, goal, strategy, or context")
        if any(x.observed_tick > decision_tick for x in items):
            raise ValueError("decision cannot precede its supporting observations")
        if len(items) != proposal.sample_count:
            raise ValueError("proposal sample count disagrees with its evidence")
        success = sum(x.confidence for x in items if x.outcome == "success")
        failure = sum(x.confidence for x in items if x.outcome == "failure")
        if not math.isclose(success, proposal.success_weight, abs_tol=1e-12) or not math.isclose(failure, proposal.failure_weight, abs_tol=1e-12):
            raise ValueError("proposal weights disagree with supporting observations")
        rule = StrategyLearningRule(
            proposal.rule_id, proposal.minimum_observations,
            proposal.prior_alpha, proposal.prior_beta,
            proposal.minimum_confidence_delta,
        )
        recomputed = self.assess(
            proposal.owner_id, proposal.strategy_id, proposal.context_key, rule,
        )
        if recomputed != proposal:
            raise ValueError("strategy proposal is stale or its derived confidence is invalid")
        decision_id = _digest({"proposal": proposal.proposal_id, "accepted": accepted,
                               "tick": decision_tick, "rationale": rationale})
        decision = StrategyBeliefDecision(
            decision_id, proposal.proposal_id, proposal.rule_id, proposal.owner_id,
            proposal.goal_id, proposal.strategy_id, proposal.context_key, accepted,
            decision_tick, rationale, proposal.posterior_confidence, proposal.observation_ids,
            proposal.minimum_observations, proposal.minimum_confidence_delta,
            proposal.prior_alpha, proposal.prior_beta)
        existing = self._decisions.get(decision_id)
        if existing is not None:
            if existing != decision:
                raise ValueError("strategy decision ID reused with conflicting content")
            return existing
        prior_id = self._proposal_decisions.get(proposal.proposal_id)
        if prior_id is not None:
            raise ValueError("strategy proposal already has a decision")
        return self._store_decision(decision)

    def _store_decision(self, decision):
        if not isinstance(decision, StrategyBeliefDecision):
            raise TypeError("decision must be StrategyBeliefDecision")
        existing = self._decisions.get(decision.decision_id)
        if existing is not None:
            if existing != decision:
                raise ValueError("strategy decision ID reused with conflicting content")
            return existing
        if decision.proposal_id in self._proposal_decisions:
            raise ValueError("strategy proposal already has a decision")
        if any(x not in self._observations for x in decision.observation_ids):
            raise ValueError("strategy decision references unknown observations")
        evidence = [self._observations[x] for x in decision.observation_ids]
        if any((item.owner_id, item.goal_id, item.strategy_id, item.context_key) !=
               (decision.owner_id, decision.goal_id, decision.strategy_id, decision.context_key)
               for item in evidence):
            raise ValueError("strategy decision references another owner, goal, strategy, or context")
        if len(evidence) < decision.minimum_observations:
            raise ValueError("strategy decision does not meet its minimum observation count")
        success = sum(item.confidence for item in evidence if item.outcome == "success")
        failure = sum(item.confidence for item in evidence if item.outcome == "failure")
        prior = decision.prior_alpha / (decision.prior_alpha + decision.prior_beta)
        posterior = (decision.prior_alpha + success) / (
            decision.prior_alpha + decision.prior_beta + success + failure)
        if (abs(posterior - prior) < decision.minimum_confidence_delta
                or not math.isclose(posterior, decision.confidence, abs_tol=1e-12)):
            raise ValueError("strategy decision confidence is inconsistent with its evidence")
        reflections = tuple(sorted({item.reflection_id for item in evidence if item.reflection_id is not None}))
        proposal_payload = {
            "owner": decision.owner_id, "goal": decision.goal_id,
            "strategy": decision.strategy_id, "context": decision.context_key,
            "rule": decision.rule_id,
            "minimum_observations": decision.minimum_observations,
            "minimum_confidence_delta": decision.minimum_confidence_delta,
            "prior_alpha": decision.prior_alpha, "prior_beta": decision.prior_beta,
            "observations": list(decision.observation_ids), "reflections": list(reflections),
            "success": success, "failure": failure, "posterior": posterior,
            "prior": prior, "delta": posterior - prior, "samples": len(evidence),
        }
        if _digest(proposal_payload) != decision.proposal_id:
            raise ValueError("strategy decision proposal digest does not match its evidence")
        self._decisions[decision.decision_id] = decision
        self._proposal_decisions[decision.proposal_id] = decision.decision_id
        return decision

    def decisions(self):
        return tuple(sorted(self._decisions.values(), key=lambda x: (x.decision_tick, x.decision_id)))

    def belief_for(self, owner_id, strategy_id, context_key):
        accepted = [x for x in self._decisions.values() if x.accepted and
                    (x.owner_id, x.strategy_id, x.context_key) == (owner_id, strategy_id, context_key)]
        if not accepted:
            return None
        latest = max(accepted, key=lambda x: (x.decision_tick, x.decision_id))
        source = self._observations[latest.observation_ids[0]]
        return StrategyBelief(latest.owner_id, latest.goal_id, latest.strategy_id,
                              latest.context_key, latest.confidence, latest.decision_id,
                              latest.decision_tick, source.action_sequence)

    def plan_reliabilities(self, owner_id, context_key):
        """Return accepted owner/context beliefs in the planner's native key shape."""
        _nonempty(owner_id, "owner_id")
        _nonempty(context_key, "context_key")
        result = {}
        for decision in self._decisions.values():
            if not decision.accepted or (decision.owner_id, decision.context_key) != (owner_id, context_key):
                continue
            current = self.belief_for(owner_id, decision.strategy_id, context_key)
            if current is not None and current.decision_id == decision.decision_id:
                result[(decision.goal_id, current.action_sequence)] = current.confidence
        return result

    def plan_reliability_sources(self, owner_id, context_key):
        """Return decision IDs for the accepted reliability values sent to the planner."""
        _nonempty(owner_id, "owner_id")
        _nonempty(context_key, "context_key")
        result = {}
        for decision in self._decisions.values():
            if not decision.accepted or (decision.owner_id, decision.context_key) != (owner_id, context_key):
                continue
            current = self.belief_for(owner_id, decision.strategy_id, context_key)
            if current is not None and current.decision_id == decision.decision_id:
                result[(decision.goal_id, current.action_sequence)] = decision.decision_id
        return result


@dataclass(frozen=True)
class StrategyBeliefSnapshot:
    observations: tuple[tuple[object, ...], ...]
    decisions: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, ledger):
        if not isinstance(ledger, NPCStrategyBeliefLedger):
            raise TypeError("ledger must be NPCStrategyBeliefLedger")
        observations = tuple(tuple(getattr(x, field) for field in (
            "observation_id", "owner_id", "goal_id", "strategy_id", "context_key",
            "plan_id", "action_sequence", "outcome", "confidence", "observed_tick", "evidence_event_ids",
            "reflection_id")) for x in sorted(ledger.observations(), key=lambda x: x.observation_id))
        decisions = tuple(tuple(getattr(x, field) for field in (
            "decision_id", "proposal_id", "rule_id", "owner_id", "goal_id", "strategy_id",
            "context_key", "accepted", "decision_tick", "rationale", "confidence",
            "observation_ids", "minimum_observations", "minimum_confidence_delta",
            "prior_alpha", "prior_beta")) for x in sorted(ledger.decisions(), key=lambda x: x.decision_id))
        return cls(observations, decisions)

    def __post_init__(self):
        if not isinstance(self.observations, tuple) or not isinstance(self.decisions, tuple):
            raise ValueError("strategy snapshot collections must be tuples")
        if any(not isinstance(x, tuple) or len(x) != 12 for x in self.observations):
            raise ValueError("invalid strategy observation snapshot")
        if any(not isinstance(x, tuple) or len(x) != 16 for x in self.decisions):
            raise ValueError("invalid strategy decision snapshot")
        observations = tuple(StrategyObservation(*x) for x in self.observations)
        decisions = tuple(StrategyBeliefDecision(*x) for x in self.decisions)
        if [x.observation_id for x in observations] != sorted({x.observation_id for x in observations}):
            raise ValueError("strategy observations must be uniquely sorted")
        if [x.decision_id for x in decisions] != sorted({x.decision_id for x in decisions}):
            raise ValueError("strategy decisions must be uniquely sorted")
        ledger = NPCStrategyBeliefLedger(observations, decisions)
        if len(ledger.observations()) != len(observations) or len(ledger.decisions()) != len(decisions):
            raise ValueError("invalid strategy snapshot history")

    def to_json(self):
        return json.dumps({"schema_version": self.SCHEMA_VERSION,
                           "observations": [list(x) for x in self.observations],
                           "decisions": [list(x) for x in self.decisions]},
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            version = raw.get("schema_version") if isinstance(raw, dict) else None
            if isinstance(version, bool) or version != cls.SCHEMA_VERSION:
                raise ValueError("unsupported strategy belief snapshot schema")
            result = cls(tuple(tuple(x) for x in raw["observations"]),
                         tuple(tuple(x) for x in raw["decisions"]))
            if result.to_json() != payload:
                raise ValueError("strategy belief snapshot must be canonical JSON")
            return result
        except (KeyError, TypeError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid strategy belief snapshot") from exc

    def restore(self):
        observations = tuple(StrategyObservation(*x) for x in self.observations)
        decisions = tuple(StrategyBeliefDecision(*x) for x in self.decisions)
        return NPCStrategyBeliefLedger(observations, decisions)
