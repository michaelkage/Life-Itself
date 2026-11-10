from simreality.goals import GoalBook, NPCGoal
from simreality.identity_context import NPCEmotionalState
from simreality.emotional_stress import CopingProfile, NPCStressLedger
from simreality.stress_adaptation import StressAdaptationProfile, StressBehaviorAdapter
from simreality.npc_motivation import (
    MotivationalGoalRule, NPCMotivationalAdapter,
)


def test_emotion_stress_and_experience_combine_as_bounded_goal_projection():
    goals = GoalBook()
    goals.add(NPCGoal("seek-support", "npc", "social", 4.0))
    goals.add(NPCGoal("keep-working", "npc", "work", 4.0))

    emotions = NPCEmotionalState("npc", 5, {"loneliness": 0.8})
    stress = NPCStressLedger(current_tick=5, initial_stress={"npc": 0.8})
    coping = CopingProfile("npc", exhaustion_threshold=0.5, breaking_point=1.0)
    adaptation = StressAdaptationProfile(
        "npc", {"social_engagement": -0.5},
        {"social_engagement": -0.5},
    )
    stress_signal = StressBehaviorAdapter.assess(stress, coping, adaptation)
    rules = (
        MotivationalGoalRule("seek-support", emotion_axis="loneliness",
                             emotion_coefficient=0.5,
                             stress_channel="social_engagement",
                             stress_coefficient=-0.5),
    )
    result = NPCMotivationalAdapter.assess(
        goals, "npc", 5, rules=rules, emotional_state=emotions,
        stress_signal=stress_signal,
        experience_adjustments={"seek-support": 0.2},
    )

    assert result.owner_id == "npc"
    assert result.sampled_tick == 5
    assert result.adjustment_for("seek-support") == 0.25
    assert len(result.contributions) == 3
    assert goals.goals["seek-support"].priority == 4.0
    assert goals.goals["seek-support"].progress == 0.0


def test_motivational_projection_rejects_future_or_foreign_state():
    goals = GoalBook()
    goals.add(NPCGoal("goal", "npc", "care", 3.0))
    rule = (MotivationalGoalRule("goal", emotion_axis="fear",
                                 emotion_coefficient=0.5),)
    future = NPCEmotionalState("npc", 8, {"fear": 0.5})
    try:
        NPCMotivationalAdapter.assess(
            goals, "npc", 7, rules=rule, emotional_state=future)
    except ValueError as exc:
        assert "future" in str(exc)
    else:
        raise AssertionError("future emotional state must be rejected")


def test_motivational_projection_can_be_passed_into_goal_selection():
    from simreality.npc_autonomy import NPCDecisionCycle
    from simreality.planning import DeterministicPlanner, PlanningAction

    goals = GoalBook()
    goals.add(NPCGoal("care", "npc", "care", 3.9))
    goals.add(NPCGoal("routine", "npc", "routine", 4.0))
    planner = DeterministicPlanner((
        PlanningAction("do-both", frozenset({"start"}),
                       frozenset({"care-done", "routine-done"})),
    ))
    decision = NPCDecisionCycle(goals, planner).decide(
        "npc", 1, {"start"},
        {"care": {"care-done"}, "routine": {"routine-done"}},
        goal_motivational_adjustments={"care": 0.1},
    )
    assert decision.goal_id == "care"
