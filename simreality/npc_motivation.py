"""Unified, read-only motivational projection for NPC goal selection.

Emotion, stress, and strategic experience remain separate evidence streams.
Explicit per-goal rules combine them into a bounded temporary score modifier;
no ledger, goal, personality, or world fact is mutated.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

from .identity_context import NPCEmotionalState
from .stress_adaptation import StressBehaviorSignal
from .goals import GoalBook


@dataclass(frozen=True)
class MotivationalGoalRule:
    goal_id: str
    emotion_axis: str | None = None
    stress_channel: str | None = None
    emotion_coefficient: float = 0.0
    stress_coefficient: float = 0.0

    def __post_init__(self):
        if not isinstance(self.goal_id, str) or not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if self.emotion_axis is not None and (not isinstance(self.emotion_axis, str) or not self.emotion_axis.strip()):
            raise ValueError("emotion_axis must be non-empty when supplied")
        if self.stress_channel is not None and (not isinstance(self.stress_channel, str) or not self.stress_channel.strip()):
            raise ValueError("stress_channel must be non-empty when supplied")
        for name in ("emotion_coefficient", "stress_coefficient"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1.0 <= value <= 1.0:
                raise ValueError(f"{name} must be finite and in [-1, 1]")
        if self.emotion_axis is None and self.stress_channel is None:
            raise ValueError("a motivational rule must reference emotion or stress")
        if self.emotion_axis is None and self.emotion_coefficient != 0:
            raise ValueError("emotion coefficient requires an emotion axis")
        if self.stress_channel is None and self.stress_coefficient != 0:
            raise ValueError("stress coefficient requires a stress channel")


@dataclass(frozen=True)
class NPCMotivationalState:
    owner_id: str
    sampled_tick: int
    adjustments: tuple[tuple[str, float], ...]
    contributions: tuple[tuple[str, str, float], ...]
    experience_adjustments: tuple[tuple[str, float], ...]

    def adjustment_for(self, goal_id: str) -> float:
        return dict(self.adjustments).get(goal_id, 0.0)


class NPCMotivationalAdapter:
    """Combine explicitly authored emotional/stress rules with experience priors."""

    @staticmethod
    def assess(
        goals: GoalBook,
        owner_id: str,
        current_tick: int,
        *,
        rules: tuple[MotivationalGoalRule, ...],
        emotional_state: NPCEmotionalState | None = None,
        stress_signal: StressBehaviorSignal | None = None,
        experience_adjustments: Mapping[str, float] | None = None,
    ) -> NPCMotivationalState:
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be a GoalBook")
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be non-negative")
        if not isinstance(rules, tuple) or any(not isinstance(rule, MotivationalGoalRule) for rule in rules):
            raise TypeError("rules must be a tuple of MotivationalGoalRule values")
        if len({(r.goal_id, r.emotion_axis, r.stress_channel) for r in rules}) != len(rules):
            raise ValueError("duplicate motivational goal rule")
        if emotional_state is not None:
            if not isinstance(emotional_state, NPCEmotionalState) or emotional_state.npc_id != owner_id:
                raise ValueError("emotional state owner must match")
            if emotional_state.sampled_tick > current_tick:
                raise ValueError("emotional state cannot come from the future")
        if stress_signal is not None:
            if not isinstance(stress_signal, StressBehaviorSignal) or stress_signal.owner_id != owner_id:
                raise ValueError("stress signal owner must match")
            if stress_signal.sampled_tick > current_tick:
                raise ValueError("stress signal cannot come from the future")
        emotion = dict(emotional_state.intensities) if emotional_state else {}
        stress = dict(stress_signal.modifiers) if stress_signal else {}
        totals: dict[str, float] = {}
        contributions = []
        for rule in rules:
            goal = goals.goals.get(rule.goal_id)
            if goal is None or goal.owner_id != owner_id:
                raise ValueError("motivational rule must reference an existing goal owned by the NPC")
            if rule.emotion_axis is not None:
                value = emotion.get(rule.emotion_axis, 0.0) * rule.emotion_coefficient
                contributions.append((rule.goal_id, "emotion:" + rule.emotion_axis, value))
                totals[rule.goal_id] = totals.get(rule.goal_id, 0.0) + value
            if rule.stress_channel is not None:
                value = stress.get(rule.stress_channel, 0.0) * rule.stress_coefficient
                contributions.append((rule.goal_id, "stress:" + rule.stress_channel, value))
                totals[rule.goal_id] = totals.get(rule.goal_id, 0.0) + value
        experience = {}
        for goal_id, value in (experience_adjustments or {}).items():
            if goal_id not in goals.goals or goals.goals[goal_id].owner_id != owner_id:
                raise ValueError("experience adjustment must reference an owned goal")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -0.25 <= value <= 0.25:
                raise ValueError("experience adjustment must be finite and in [-0.25, 0.25]")
            experience[goal_id] = float(value)
        for goal_id, value in experience.items():
            contributions.append((goal_id, "experience", value))
            totals[goal_id] = totals.get(goal_id, 0.0) + value
        bounded = tuple(sorted((goal_id, max(-0.25, min(0.25, value)))
                               for goal_id, value in totals.items()))
        return NPCMotivationalState(
            owner_id, current_tick, bounded,
            tuple(sorted(contributions)), tuple(sorted(experience.items())),
        )
