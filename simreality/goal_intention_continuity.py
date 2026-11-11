"""Continuity-aware reassessment of an NPC's current goal commitment.

Every call performs fresh arbitration from current inputs. The previous
commitment is only a bounded tie-breaker: it never overrides feasibility or a
challenger that clears the configured switching margin.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .goal_arbitration import (
    GoalArbitrationAssessment,
    GoalArbitrationEvaluator,
    GoalArbitrationRule,
    GoalCommitment,
    GoalCommitmentAdapter,
    GoalCommitmentLedger,
)
from .goals import GoalBook
from .identity_context import NPCEmotionalState
from .goal_intention_memory import GoalIntentionMemoryLedger
from .goal_intention_recall import (
    GoalIntentionRecall, GoalIntentionRecallAdapter, GoalIntentionRecallRule,
)


@dataclass(frozen=True)
class GoalContinuityResult:
    """Fresh assessment and its persisted focus decision."""

    assessment: GoalArbitrationAssessment
    commitment: GoalCommitment
    previous_commitment: GoalCommitment | None
    retained_previous_focus: bool
    intention_recall: GoalIntentionRecall | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, GoalArbitrationAssessment):
            raise TypeError("assessment must be GoalArbitrationAssessment")
        if not isinstance(self.commitment, GoalCommitment):
            raise TypeError("commitment must be GoalCommitment")
        if self.previous_commitment is not None and not isinstance(
            self.previous_commitment, GoalCommitment
        ):
            raise TypeError("previous_commitment must be GoalCommitment or None")
        if not isinstance(self.retained_previous_focus, bool):
            raise TypeError("retained_previous_focus must be bool")
        if self.intention_recall is not None:
            if not isinstance(self.intention_recall, GoalIntentionRecall):
                raise TypeError("intention_recall must be GoalIntentionRecall or None")
            if (self.intention_recall.owner_id != self.commitment.owner_id
                    or self.intention_recall.tick != self.commitment.tick):
                raise ValueError("intention recall must match the committed owner and tick")
        if self.commitment.assessment_id != self.assessment.assessment_id:
            raise ValueError("commitment must reference the supplied fresh assessment")
        if self.commitment.selected_goal_id != self.assessment.selected_goal_id:
            raise ValueError("commitment selection must match the supplied assessment")


class GoalIntentionContinuityAdapter:
    """Reassess each tick while applying bounded commitment hysteresis."""

    @staticmethod
    def reconsider(
        goals: GoalBook,
        ledger: GoalCommitmentLedger,
        owner_id: str,
        current_tick: int,
        *,
        rationale: str,
        continuity_margin: float = 0.08,
        rules: tuple[GoalArbitrationRule, ...] = (),
        need_deficits: Mapping[str, float] | None = None,
        emotional_state: NPCEmotionalState | None = None,
        value_alignment: Mapping[str, float] | None = None,
        resources: Mapping[str, float] | None = None,
        experience_adjustments: Mapping[str, float] | None = None,
        intention_memories: GoalIntentionMemoryLedger | None = None,
        recall_rules: tuple[GoalIntentionRecallRule, ...] = (),
    ) -> GoalContinuityResult:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if not isinstance(ledger, GoalCommitmentLedger):
            raise TypeError("ledger must be GoalCommitmentLedger")
        history = ledger.for_owner(owner_id)
        previous = next((item for item in reversed(history)
                         if item.tick < current_tick), None)
        existing_current = ledger.at_tick(owner_id, current_tick)
        latest = ledger.latest_for_owner(owner_id)
        if latest is not None and latest.tick > current_tick:
            raise ValueError("cannot reconsider a goal before the latest commitment tick")
        # Reconstruct the original tick's incumbent, not the commitment created
        # by that same tick. This makes same-tick replay reproduce its digest.
        incumbent_id = previous.selected_goal_id if previous is not None else None
        if intention_memories is not None and not isinstance(intention_memories, GoalIntentionMemoryLedger):
            raise TypeError("intention_memories must be GoalIntentionMemoryLedger or None")
        if not isinstance(recall_rules, tuple) or any(
            not isinstance(item, GoalIntentionRecallRule) for item in recall_rules
        ):
            raise TypeError("recall_rules must be a tuple of GoalIntentionRecallRule values")
        recall = None
        if intention_memories is not None:
            recall = GoalIntentionRecallAdapter.recall(
                intention_memories, goals, owner_id, current_tick, rules=recall_rules,
            )
        elif recall_rules:
            raise ValueError("intention_memories are required when recall_rules are supplied")
        if experience_adjustments is not None and not isinstance(experience_adjustments, Mapping):
            raise TypeError("experience_adjustments must be a mapping")
        combined_experience = {}
        for goal_id, raw_adjustment in (experience_adjustments or {}).items():
            if not isinstance(goal_id, str) or not goal_id.strip():
                raise ValueError("experience adjustment goal IDs must be non-empty")
            if (isinstance(raw_adjustment, bool)
                    or not isinstance(raw_adjustment, (int, float))
                    or not math.isfinite(raw_adjustment)
                    or not -0.25 <= raw_adjustment <= 0.25):
                raise ValueError("experience adjustments must be finite and in [-0.25, 0.25]")
            combined_experience[goal_id] = float(raw_adjustment)
        if recall is not None:
            for goal_id, adjustment in recall.adjustments:
                combined_experience[goal_id] = max(
                    -0.25, min(0.25, combined_experience.get(goal_id, 0.0) + adjustment)
                )
        assessment = GoalArbitrationEvaluator.assess(
            goals,
            owner_id,
            current_tick,
            rules=rules,
            need_deficits=need_deficits,
            emotional_state=emotional_state,
            value_alignment=value_alignment,
            resources=resources,
            experience_adjustments=combined_experience,
            experience_evidence_id=recall.recall_id if recall is not None else None,
            incumbent_goal_id=incumbent_id,
            continuity_margin=continuity_margin,
        )
        if assessment.selected_goal_id is None:
            raise ValueError("no resource-feasible actionable goal can be committed")
        if existing_current is not None:
            # A tick is a single decision boundary. Replaying identical inputs is
            # safe; changing inputs after commitment would fork the same history.
            if existing_current.assessment_id != assessment.assessment_id:
                raise ValueError("goal commitment already exists for this NPC and tick")
            commitment = existing_current
        else:
            commitment = GoalCommitmentAdapter.commit(
                assessment, goals, ledger, rationale=rationale,
            )
        retained = (
            previous is not None
            and assessment.selected_goal_id == previous.selected_goal_id
        )
        return GoalContinuityResult(assessment, commitment, previous, retained, recall)
