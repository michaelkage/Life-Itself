"""Connect deterministic goal ranking to symbolic planning without side effects.

The decision cycle tries goals in priority order and can fall back when a higher
priority goal has no configured target facts or cannot currently be planned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .goals import GoalBook
from .planning import DeterministicPlanner, PlanResult


@dataclass(frozen=True)
class NPCDecision:
    """One inspectable NPC decision proposal; it is not an executed action."""

    owner_id: str
    tick: int
    goal_id: str | None
    goal_category: str | None
    plan: PlanResult | None
    reason: str

    @property
    def actionable(self) -> bool:
        return self.goal_id is not None and self.plan is not None and self.plan.success


class NPCDecisionCycle:
    """Join a goal book and planner into a deterministic, read-only decision step."""

    def __init__(self, goals: GoalBook, planner: DeterministicPlanner) -> None:
        self.goals = goals
        self.planner = planner

    def decide(
        self,
        owner_id: str,
        current_tick: int,
        world_facts: frozenset[str] | set[str] | tuple[str, ...],
        goal_facts: Mapping[str, frozenset[str] | set[str] | tuple[str, ...]],
        *,
        max_expansions: int = 10_000,
    ) -> NPCDecision:
        """Propose a plan for the highest-ranked goal that can currently be planned.

        goal_facts explicitly maps goal IDs to desired world facts. If a higher-ranked
        goal cannot be planned, lower-ranked goals are tried deterministically.
        If none can be planned, the highest-ranked failure is returned for inspection.
        """
        if not owner_id or not owner_id.strip():
            raise ValueError("owner_id must be non-empty")
        if current_tick < 0:
            raise ValueError("current_tick must be non-negative")

        ranked_goals = self.goals.ranked(owner_id, current_tick)
        if not ranked_goals:
            return NPCDecision(owner_id, current_tick, None, None, None,
                               "no actionable goal")

        first_failure: NPCDecision | None = None
        skipped: list[str] = []
        for goal in ranked_goals:
            if goal.goal_id not in goal_facts:
                failure = NPCDecision(
                    owner_id, current_tick, goal.goal_id, goal.category, None,
                    "selected goal has no desired-facts mapping",
                )
            else:
                plan = self.planner.plan(
                    world_facts, goal_facts[goal.goal_id],
                    max_expansions=max_expansions,
                )
                reason = plan.reason if plan.success else f"planning failed: {plan.reason}"
                candidate = NPCDecision(
                    owner_id, current_tick, goal.goal_id, goal.category, plan, reason
                )
                if plan.success:
                    if skipped:
                        return NPCDecision(
                            owner_id, current_tick, goal.goal_id, goal.category, plan,
                            "feasible fallback; higher-ranked goals unavailable: "
                            + ", ".join(skipped),
                        )
                    return candidate
                failure = candidate

            if first_failure is None:
                first_failure = failure
            skipped.append(f"{goal.goal_id} ({failure.reason})")

        if first_failure is None:
            raise RuntimeError("ranked goals produced no decision")
        return first_failure
