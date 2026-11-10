from simreality.goals import GoalBook, NPCGoal, GoalStatus
from simreality.identity_context import NPCEmotionalState
from simreality.npc_life_history import NPCLifeHistory, AutobiographicalMemory
from simreality.npc_goal_emergence import (
    GoalTemplate, GoalEmergenceRule, NPCGoalEmergence,
    GoalLifecycleLedger,
)


def test_goal_emergence_is_deterministic_read_only_and_explicitly_adopted():
    goals = GoalBook()
    rule = GoalEmergenceRule(
        "seek-shelter", GoalTemplate("shelter", "safety", 5.0),
        need_key="safety", need_threshold=0.7,
    )
    before = goals.snapshot()
    first = NPCGoalEmergence.propose(
        goals, "npc", 10, rules=(rule,), need_deficits={"safety": 0.9})
    second = NPCGoalEmergence.propose(
        goals, "npc", 10, rules=(rule,), need_deficits={"safety": 0.9})
    assert first == second
    assert goals.snapshot() == before
    assert first[0].trigger_types == ("need:safety",)
    adopted = first[0].to_goal()
    goals.add(adopted)
    assert goals.goals[adopted.goal_id] == adopted
    assert NPCGoalEmergence.propose(
        goals, "npc", 11, rules=(rule,), need_deficits={"safety": 0.9}) == ()


def test_emotion_stress_and_personal_turning_point_can_trigger_rules():
    goals = GoalBook()
    history = NPCLifeHistory((AutobiographicalMemory(
        "memory-1", "npc", "event-1", 4, (), "A major loss",
        0.9, 0.5, turning_point=True, tags=("loss", "seek:community"),
    ),))
    rules = (
        GoalEmergenceRule("grief", GoalTemplate("community", "social", 4),
                          emotion_axis="grief", emotion_threshold=0.6),
        GoalEmergenceRule("pressure", GoalTemplate("rest", "recovery", 3),
                          stress_channel="sleep_priority", stress_threshold=0.5),
        GoalEmergenceRule("memory", GoalTemplate("meaning", "identity", 2),
                          experience_tag="seek:community", require_turning_point=True),
    )
    emotional = NPCEmotionalState("npc", 5, {"grief": 0.8})
    from simreality.stress_adaptation import StressBehaviorSignal
    stress = StressBehaviorSignal("npc", 5, 0.8, 0.2,
                                 (("sleep_priority", 0.7),), ())
    proposals = NPCGoalEmergence.propose(
        goals, "npc", 5, rules=rules, emotional_state=emotional,
        stress_signal=stress, history=history)
    assert {p.rule_id for p in proposals} == {"grief", "pressure", "memory"}
    assert all(p.source_classes == ("personal_memory",) for p in proposals if p.rule_id == "memory")
    assert all(p.evidence_ids == ("memory-1",) for p in proposals if p.rule_id == "memory")


def test_future_memories_are_excluded_and_lifecycle_is_append_only():
    goals = GoalBook()
    future = NPCLifeHistory((AutobiographicalMemory(
        "future", "npc", "event", 9, (), "future", 0.2, 0.0,
        tags=("opportunity",),
    ),))
    rule = GoalEmergenceRule("opportunity", GoalTemplate("venture", "growth", 2),
                             experience_tag="opportunity")
    assert NPCGoalEmergence.propose(
        goals, "npc", 8, rules=(rule,), history=future) == ()

    goal = NPCGoal("g", "npc", "care", 2)
    goals.add(goal)
    ledger = GoalLifecycleLedger()
    adopted = ledger.record(goal, 1, "adopted", evidence_ids=("memory-1",))
    goal.status = GoalStatus.ABANDONED
    retired = ledger.record(goal, 2, "circumstances changed")
    assert adopted.from_status is None and adopted.to_status == "active"
    assert retired.from_status == "active" and retired.to_status == "abandoned"
    assert ledger.status_for("g") == "abandoned"
    assert len(ledger.snapshot()) == 2
