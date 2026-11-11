"""Deterministic, evidence-grounded NPC goal proposals and lifecycle history.

Proposal generation is read-only. Authored rules map explicit need, emotion,
stress, and autobiographical-memory tags to goal templates; no language model,
randomness, or inferred semantic matching is used.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Mapping

from .goals import GoalBook, NPCGoal, GoalStatus
from .identity_context import NPCEmotionalState
from .stress_adaptation import StressBehaviorSignal
from .npc_life_history import NPCLifeHistory
from .npc_experience_transfer import StrategicExperienceEvidence


@dataclass(frozen=True)
class GoalTemplate:
    template_id: str
    category: str
    priority: float
    confidence: float = 0.5
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        if any(not isinstance(x, str) or not x.strip()
               for x in (self.template_id, self.category)):
            raise ValueError("template_id and category must be non-empty")
        if isinstance(self.priority, bool) or not isinstance(self.priority, (int, float)) or not math.isfinite(self.priority) or self.priority < 0:
            raise ValueError("priority must be finite and non-negative")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite and in [0, 1]")
        if not isinstance(self.metadata, tuple) or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str)
            for k, v in self.metadata
        ):
            raise ValueError("metadata must be a tuple of string pairs")
        if len({k for k, _ in self.metadata}) != len(self.metadata):
            raise ValueError("metadata keys must be unique")


@dataclass(frozen=True)
class GoalEmergenceRule:
    rule_id: str
    template: GoalTemplate
    need_key: str | None = None
    need_threshold: float = 0.5
    emotion_axis: str | None = None
    emotion_threshold: float = 0.5
    stress_channel: str | None = None
    stress_threshold: float = 0.5
    experience_tag: str | None = None
    require_turning_point: bool = False

    def __post_init__(self):
        if not isinstance(self.rule_id, str) or not self.rule_id.strip():
            raise ValueError("rule_id must be non-empty")
        if not isinstance(self.template, GoalTemplate):
            raise TypeError("template must be GoalTemplate")
        triggers = (self.need_key, self.emotion_axis, self.stress_channel, self.experience_tag)
        if not any(x is not None for x in triggers):
            raise ValueError("a rule must define at least one trigger")
        for name in ("need_key", "emotion_axis", "stress_channel", "experience_tag"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be non-empty when supplied")
        for name in ("need_threshold", "emotion_threshold", "stress_threshold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be finite and in [0, 1]")
        if not isinstance(self.require_turning_point, bool):
            raise TypeError("require_turning_point must be bool")


@dataclass(frozen=True)
class NPCGoalProposal:
    proposal_id: str
    owner_id: str
    goal_id: str
    rule_id: str
    template: GoalTemplate
    proposed_tick: int
    trigger_types: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    source_classes: tuple[str, ...]
    explanation: str

    def to_goal(self) -> NPCGoal:
        return NPCGoal(
            self.goal_id, self.owner_id, self.template.category,
            float(self.template.priority), created_tick=self.proposed_tick,
            review_tick=self.proposed_tick, confidence=float(self.template.confidence),
            metadata=dict(self.template.metadata) | {
                "emergence_proposal_id": self.proposal_id,
                "emergence_rule_id": self.rule_id,
            },
        )


class NPCGoalEmergence:
    """Evaluate explicit goal-emergence rules without mutating simulation state."""

    @staticmethod
    def propose(
        goals: GoalBook, owner_id: str, current_tick: int, *,
        rules: tuple[GoalEmergenceRule, ...],
        need_deficits: Mapping[str, float] | None = None,
        emotional_state: NPCEmotionalState | None = None,
        stress_signal: StressBehaviorSignal | None = None,
        history: NPCLifeHistory | None = None,
        experience_evidence: tuple[StrategicExperienceEvidence, ...] = (),
    ) -> tuple[NPCGoalProposal, ...]:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        if not isinstance(rules, tuple) or any(not isinstance(r, GoalEmergenceRule) for r in rules):
            raise TypeError("rules must be a tuple of GoalEmergenceRule")
        if len({r.rule_id for r in rules}) != len(rules):
            raise ValueError("rule IDs must be unique")
        needs = {} if need_deficits is None else dict(need_deficits)
        for key, value in needs.items():
            if not isinstance(key, str) or not key.strip() or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("need deficits must be named finite values in [0, 1]")
        if emotional_state is not None and (not isinstance(emotional_state, NPCEmotionalState) or emotional_state.npc_id != owner_id or emotional_state.sampled_tick > current_tick):
            raise ValueError("emotional snapshot must belong to owner and not be from the future")
        if stress_signal is not None and (not isinstance(stress_signal, StressBehaviorSignal) or stress_signal.owner_id != owner_id or stress_signal.sampled_tick > current_tick):
            raise ValueError("stress signal must belong to owner and not be from the future")
        if history is not None and not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be NPCLifeHistory")
        if not isinstance(experience_evidence, tuple) or any(not isinstance(x, StrategicExperienceEvidence) or x.owner_id != owner_id or x.tick > current_tick for x in experience_evidence):
            raise ValueError("experience evidence must be a tuple of owner-matched, non-future strategic evidence")
        emotions = dict(emotional_state.intensities) if emotional_state else {}
        stress = dict(stress_signal.modifiers) if stress_signal else {}
        memories = tuple(m for m in history.memories(owner_id) if m.tick <= current_tick) if history else ()
        existing = [g for g in goals.goals.values() if g.owner_id == owner_id]
        results = []
        proposed_templates: set[tuple[str, str]] = set()
        for rule in sorted(rules, key=lambda x: x.rule_id):
            triggers, evidence, sources = [], [], []
            if rule.need_key is not None and needs.get(rule.need_key, 0.0) >= rule.need_threshold:
                triggers.append("need:" + rule.need_key)
            if rule.emotion_axis is not None and emotions.get(rule.emotion_axis, 0.0) >= rule.emotion_threshold:
                triggers.append("emotion:" + rule.emotion_axis)
            if rule.stress_channel is not None and stress.get(rule.stress_channel, 0.0) >= rule.stress_threshold:
                triggers.append("stress:" + rule.stress_channel)
            if rule.experience_tag is not None:
                matches = [m for m in memories if rule.experience_tag in m.tags
                           and (m.turning_point or not rule.require_turning_point)]
                strategic = [x for x in experience_evidence
                             if rule.experience_tag in x.tags
                             and not rule.require_turning_point]
                evidence.extend(m.memory_id for m in matches)
                sources.extend("personal_memory" for _ in matches)
                evidence.extend(x.evidence_id for x in strategic)
                sources.extend(x.source_class for x in strategic)
                if matches or strategic:
                    triggers.append("experience:" + rule.experience_tag)
            if not triggers:
                continue
            template_key = (rule.template.category, rule.template.template_id)
            if template_key in proposed_templates:
                continue
            matching = [
                g for g in existing
                if g.category == rule.template.category
                and g.metadata.get("emergence_template_id") == rule.template.template_id
            ]
            if any(g.status not in {GoalStatus.FAILED, GoalStatus.ABANDONED}
                   for g in matching):
                continue
            proposed_templates.add(template_key)
            incarnation = len(matching)
            payload = (owner_id, rule.rule_id, rule.template.template_id, str(incarnation))
            digest = hashlib.sha256("|".join(payload).encode("utf-8")).hexdigest()[:20]
            proposal_id = "goal-proposal-" + digest
            goal_id = "goal-" + digest
            template_metadata = dict(rule.template.metadata)
            template_metadata["emergence_template_id"] = rule.template.template_id
            template = GoalTemplate(
                rule.template.template_id, rule.template.category,
                rule.template.priority, rule.template.confidence,
                tuple(sorted(template_metadata.items())),
            )
            results.append(NPCGoalProposal(
                proposal_id, owner_id, goal_id, rule.rule_id, template,
                current_tick, tuple(sorted(triggers)), tuple(sorted(set(evidence))),
                tuple(sorted(set(sources))),
                "Authored rule " + rule.rule_id + " matched " + ", ".join(sorted(triggers)),
            ))
        return tuple(results)


@dataclass(frozen=True)
class GoalLifecycleEvent:
    event_id: str
    goal_id: str
    owner_id: str
    from_status: str | None
    to_status: str
    tick: int
    reason: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("event_id", "goal_id", "owner_id", "to_status", "reason"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be non-empty")
        if self.from_status not in (None, "active", "completed", "failed", "abandoned", "blocked"):
            raise ValueError("invalid from_status")
        if self.to_status not in ("active", "completed", "failed", "abandoned", "blocked"):
            raise ValueError("invalid to_status")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be non-negative")
        if not isinstance(self.evidence_ids, tuple) or any(not isinstance(x, str) or not x.strip() for x in self.evidence_ids):
            raise ValueError("evidence_ids must be a tuple of non-empty strings")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")


class GoalLifecycleLedger:
    """Append-only explanation of goal adoption, suspension, retirement and reopening."""

    def __init__(self, events: tuple[GoalLifecycleEvent, ...] = ()):
        self._events: list[GoalLifecycleEvent] = []
        self._event_by_id: dict[str, GoalLifecycleEvent] = {}
        self._status: dict[str, str] = {}
        self._owners: dict[str, str] = {}
        self._last_tick: dict[str, int] = {}
        self._goal_event_counts: dict[str, int] = {}
        self._last_event_by_goal: dict[str, GoalLifecycleEvent] = {}
        for event in events:
            self.append(event)

    def append(self, event: GoalLifecycleEvent) -> None:
        if not isinstance(event, GoalLifecycleEvent):
            raise TypeError("event must be GoalLifecycleEvent")
        existing = self._event_by_id.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise ValueError("lifecycle event ID reused with conflicting content")
            return
        prior = self._status.get(event.goal_id)
        if event.from_status != prior:
            raise ValueError("lifecycle transition does not match prior status")
        if event.goal_id in self._owners and event.owner_id != self._owners[event.goal_id]:
            raise ValueError("goal lifecycle owner cannot change")
        if event.goal_id in self._last_tick and event.tick < self._last_tick[event.goal_id]:
            raise ValueError("goal lifecycle ticks must be non-decreasing")
        allowed = {
            None: {"active"},
            "active": {"active", "completed", "failed", "abandoned", "blocked"},
            "blocked": {"active", "abandoned"},
            "abandoned": {"active"},
            "completed": set(),
            "failed": set(),
        }
        if event.to_status not in allowed[prior]:
            raise ValueError("invalid goal lifecycle status transition")
        self._events.append(event)
        self._event_by_id[event.event_id] = event
        self._status[event.goal_id] = event.to_status
        self._owners[event.goal_id] = event.owner_id
        self._last_tick[event.goal_id] = event.tick
        self._goal_event_counts[event.goal_id] = self._goal_event_counts.get(event.goal_id, 0) + 1
        self._last_event_by_goal[event.goal_id] = event

    def record(self, goal: NPCGoal, tick: int, reason: str, *,
               evidence_ids: tuple[str, ...] = ()) -> GoalLifecycleEvent:
        if not isinstance(goal, NPCGoal):
            raise TypeError("goal must be NPCGoal")
        goal.validate()
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < goal.created_tick:
            raise ValueError("lifecycle tick must be an integer at or after goal creation")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        if not isinstance(evidence_ids, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in evidence_ids
        ):
            raise ValueError("evidence_ids must be a tuple of non-empty strings")
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        prior = self._status.get(goal.goal_id)
        normalized_evidence = tuple(sorted(evidence_ids))
        previous = self._last_event_by_goal.get(goal.goal_id)
        if (previous is not None and previous.owner_id == goal.owner_id
                and previous.to_status == goal.status.value
                and previous.tick == tick and previous.reason == reason
                and previous.evidence_ids == normalized_evidence):
            return previous
        sequence = self._goal_event_counts.get(goal.goal_id, 0)
        payload = (goal.goal_id, prior or "new", goal.status.value, tick, reason,
                   normalized_evidence, sequence)
        event_id = "goal-life-" + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()[:20]
        event = GoalLifecycleEvent(event_id, goal.goal_id, goal.owner_id, prior,
                                   goal.status.value, tick, reason,
                                   normalized_evidence)
        self.append(event)
        return event

    def transition(self, goals: GoalBook, goal_id: str, target_status: GoalStatus,
                   tick: int, reason: str, *,
                   evidence_ids: tuple[str, ...] = ()) -> GoalLifecycleEvent:
        """Apply one explicit status change and record it as one atomic lifecycle step."""
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(target_status, GoalStatus):
            raise TypeError("target_status must be GoalStatus")
        if target_status == GoalStatus.BLOCKED:
            raise ValueError("blocked status is derived from goal dependencies")
        goal = goals.goals[goal_id]
        previous = self._last_event_by_goal.get(goal_id)
        normalized_evidence = tuple(sorted(evidence_ids))
        if (goal.status == target_status and previous is not None
                and previous.to_status == target_status.value
                and previous.tick == tick and previous.reason == reason
                and previous.evidence_ids == normalized_evidence):
            return previous
        if goal.status == target_status:
            raise ValueError("goal already has the requested status")
        recorded_status = self._status.get(goal_id)
        if recorded_status is not None and recorded_status != goal.status.value:
            raise ValueError("GoalBook status differs from recorded lifecycle state")
        if recorded_status is None:
            if goal.status != GoalStatus.ACTIVE:
                raise ValueError("lifecycle tracking must begin while a goal is active")
            self.record(goal, goal.created_tick, "lifecycle tracking initialized")
        old_status, old_progress, old_review_tick = goal.status, goal.progress, goal.review_tick
        try:
            if target_status == GoalStatus.ACTIVE:
                goals.reopen(goal_id, tick)
            else:
                goals.set_status(goal_id, target_status)
                goal.review_tick = max(goal.review_tick, tick)
            return self.record(goal, tick, reason, evidence_ids=evidence_ids)
        except Exception:
            goal.status, goal.progress, goal.review_tick = old_status, old_progress, old_review_tick
            raise

    def status_for(self, goal_id: str) -> str | None:
        return self._status.get(goal_id)

    def snapshot(self) -> tuple[GoalLifecycleEvent, ...]:
        return tuple(self._events)
