"""Explicit alternative-intention proposals and adoption for NPCs.

Event-driven obsolescence remains governed by GoalReviewPolicy. This module
connects an active intention to independently evidenced goal-emergence rules
and offers alternatives without replacing or mutating the source intention.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping

from .goals import GoalBook, GoalStatus, NPCGoal
from .goal_review import GoalReviewEvaluator, GoalReviewPolicy, GoalReviewProposal
from .world_events import WorldEvent
from .npc_goal_emergence import (
    GoalEmergenceRule, GoalLifecycleEvent, GoalLifecycleLedger,
    NPCGoalEmergence, NPCGoalProposal,
)
from .identity_context import NPCEmotionalState
from .stress_adaptation import StressBehaviorSignal
from .npc_life_history import NPCLifeHistory
from .npc_experience_transfer import StrategicExperienceEvidence


@dataclass(frozen=True)
class GoalAlternativeProposal:
    """An independently motivated candidate linked to an existing intention."""
    alternative_id: str
    source_goal_id: str
    source_goal_category: str
    source_goal_priority: float
    source_goal_confidence: float
    emergence: NPCGoalProposal

    def __post_init__(self) -> None:
        for name in ("alternative_id", "source_goal_id", "source_goal_category"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.emergence, NPCGoalProposal):
            raise TypeError("emergence must be NPCGoalProposal")
        for name in ("source_goal_priority", "source_goal_confidence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be finite numeric")
        if self.source_goal_priority < 0 or not 0 <= self.source_goal_confidence <= 1:
            raise ValueError("source goal values are outside their valid ranges")
        if self.emergence.goal_id == self.source_goal_id:
            raise ValueError("an alternative must have a distinct goal ID")

    @property
    def owner_id(self) -> str:
        return self.emergence.owner_id

    @property
    def proposed_goal_id(self) -> str:
        return self.emergence.goal_id

    @property
    def proposed_tick(self) -> int:
        return self.emergence.proposed_tick

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return self.emergence.evidence_ids


class GoalAlternativeEvaluator:
    """Generate alternatives only from caller-supplied, authored emergence evidence."""

    @staticmethod
    def assess(
        goals: GoalBook, source_goal_id: str, current_tick: int, *,
        rules: tuple[GoalEmergenceRule, ...],
        need_deficits: Mapping[str, float] | None = None,
        emotional_state: NPCEmotionalState | None = None,
        stress_signal: StressBehaviorSignal | None = None,
        history: NPCLifeHistory | None = None,
        experience_evidence: tuple[StrategicExperienceEvidence, ...] = (),
    ) -> tuple[GoalAlternativeProposal, ...]:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(source_goal_id, str) or not source_goal_id.strip():
            raise ValueError("source_goal_id must be non-empty")
        source = goals.goals.get(source_goal_id)
        if source is None or source.status != GoalStatus.ACTIVE:
            raise ValueError("alternative proposals require an existing active source goal")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < source.review_tick:
            raise ValueError("current_tick must be at or after the source goal review tick")
        proposals = NPCGoalEmergence.propose(
            goals, source.owner_id, current_tick, rules=rules,
            need_deficits=need_deficits, emotional_state=emotional_state,
            stress_signal=stress_signal, history=history,
            experience_evidence=experience_evidence,
        )
        alternatives = []
        for proposal in proposals:
            if proposal.goal_id == source_goal_id:
                continue
            alternative_id = f"alternative:{source_goal_id}:{proposal.proposal_id}"
            alternatives.append(GoalAlternativeProposal(
                alternative_id, source.goal_id, source.category, source.priority,
                source.confidence, proposal,
            ))
        return tuple(sorted(alternatives, key=lambda item: (
            item.proposed_tick, item.owner_id, item.proposed_goal_id, item.alternative_id
        )))


class GoalAlternativeAdapter:
    """Explicitly adopt an alternative as a new goal, preserving the source goal.

    Adoption never silently abandons, reframes, or edits the source intention.
    The caller can separately submit a review decision for the source goal.
    """

    @staticmethod
    def adopt(
        proposal: GoalAlternativeProposal, goals: GoalBook,
        lifecycle: GoalLifecycleLedger, *, reason: str | None = None,
    ) -> tuple[NPCGoal, GoalLifecycleEvent]:
        if not isinstance(proposal, GoalAlternativeProposal):
            raise TypeError("proposal must be GoalAlternativeProposal")
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(lifecycle, GoalLifecycleLedger):
            raise TypeError("lifecycle must be GoalLifecycleLedger")
        source = goals.goals.get(proposal.source_goal_id)
        if source is None or source.owner_id != proposal.owner_id:
            raise ValueError("alternative source goal or owner no longer exists")
        if (source.status != GoalStatus.ACTIVE
                or source.category != proposal.source_goal_category
                or source.priority != proposal.source_goal_priority
                or source.confidence != proposal.source_goal_confidence
                or proposal.proposed_tick < source.review_tick):
            raise ValueError("alternative proposal is stale: source intention changed")
        if proposal.proposed_goal_id in goals.goals:
            existing = goals.goals[proposal.proposed_goal_id]
            if existing.owner_id == proposal.owner_id and existing.metadata.get("emergence_proposal_id") == proposal.emergence.proposal_id:
                events = lifecycle.snapshot()
                matching = [event for event in events if event.goal_id == existing.goal_id and event.to_status == "active"]
                if matching:
                    return existing, matching[-1]
            raise ValueError("alternative goal ID already exists")
        goal = proposal.emergence.to_goal()
        if goal.owner_id != source.owner_id or goal.created_tick != proposal.proposed_tick:
            raise ValueError("alternative proposal owner or creation tick is inconsistent")
        goals.add(goal)
        try:
            event = lifecycle.record(
                goal, proposal.proposed_tick,
                reason or f"NPC explicitly adopted alternative to {source.goal_id}",
                evidence_ids=proposal.evidence_ids,
            )
        except Exception:
            del goals.goals[goal.goal_id]
            goals._validate_dependency_graph()
            raise
        return goal, event


@dataclass(frozen=True)
class GoalIntentionAssessment:
    """One read-only view of event-driven reviews and emerging alternatives."""
    review_proposals: tuple[GoalReviewProposal, ...]
    alternatives: tuple[GoalAlternativeProposal, ...]


class GoalIntentionEvaluator:
    """Assess event-based reviews and evidence-based alternatives together.

    The two result collections remain separate: reconsidering an existing
    intention is a different decision from adopting an additional intention.
    """

    @staticmethod
    def assess(
        goals: GoalBook, source_goal_id: str, current_tick: int, *,
        events: Iterable[WorldEvent],
        review_policies: tuple[GoalReviewPolicy, ...],
        emergence_rules: tuple[GoalEmergenceRule, ...],
        need_deficits: Mapping[str, float] | None = None,
        emotional_state: NPCEmotionalState | None = None,
        stress_signal: StressBehaviorSignal | None = None,
        history: NPCLifeHistory | None = None,
        experience_evidence: tuple[StrategicExperienceEvidence, ...] = (),
    ) -> GoalIntentionAssessment:
        if not isinstance(review_policies, tuple) or any(not isinstance(item, GoalReviewPolicy) for item in review_policies):
            raise TypeError("review_policies must be a tuple of GoalReviewPolicy values")
        event_items = tuple(events)
        reviews = GoalReviewEvaluator(goals, review_policies).assess(event_items)
        alternatives = GoalAlternativeEvaluator.assess(
            goals, source_goal_id, current_tick, rules=emergence_rules,
            need_deficits=need_deficits, emotional_state=emotional_state,
            stress_signal=stress_signal, history=history,
            experience_evidence=experience_evidence,
        )
        return GoalIntentionAssessment(reviews, alternatives)
