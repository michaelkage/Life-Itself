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

def test_reported_experience_keeps_reported_provenance_separate():
    from simreality.npc_experience_transfer import StrategicExperienceEvidence

    goals = GoalBook()
    evidence = StrategicExperienceEvidence(
        "npc", "report-1", "source-event", 6, "A trusted account",
        "reported", 0.8, 0.28, ("migration",),
    )
    rule = GoalEmergenceRule(
        "migration", GoalTemplate("relocate", "safety", 4),
        experience_tag="migration",
    )
    proposal, = NPCGoalEmergence.propose(
        goals, "npc", 7, rules=(rule,), experience_evidence=(evidence,))
    assert proposal.evidence_ids == ("report-1",)
    assert proposal.source_classes == ("reported",)

def test_abandoned_goal_can_be_reopened_or_replaced_by_new_incarnation():
    from simreality.goals import GoalStatus

    goals = GoalBook()
    prior = NPCGoal(
        "prior", "npc", "safety", 3.0,
        status=GoalStatus.ABANDONED,
        metadata={"emergence_template_id": "shelter"},
    )
    goals.add(prior)
    goals.reopen("prior", 12)
    assert prior.status == GoalStatus.ACTIVE
    assert prior.review_tick == 12
    goals.set_status("prior", GoalStatus.ABANDONED)
    rule = GoalEmergenceRule(
        "shelter-rule", GoalTemplate("shelter", "safety", 4.0),
        need_key="safety", need_threshold=0.7,
    )
    proposal, = NPCGoalEmergence.propose(
        goals, "npc", 13, rules=(rule,), need_deficits={"safety": 0.9})
    assert proposal.goal_id != "prior"
    assert proposal.to_goal().metadata["emergence_template_id"] == "shelter"
    goals.add(proposal.to_goal())
    assert len(goals.goals) == 2


def test_goal_lifecycle_snapshot_preserves_append_order_and_validates_transitions():
    from simreality.npc_goal_emergence import GoalLifecycleEvent, GoalLifecycleLedger
    from simreality.goal_lifecycle_save_state import GoalLifecycleSnapshot

    ledger = GoalLifecycleLedger()
    ledger.append(GoalLifecycleEvent("z-first", "g", "npc", None, "active", 2, "adopt"))
    ledger.append(GoalLifecycleEvent("a-second", "g", "npc", "active", "abandoned", 2, "retire"))
    ledger.append(GoalLifecycleEvent("m-third", "g", "npc", "abandoned", "active", 3, "return"))
    payload = GoalLifecycleSnapshot.capture(ledger).to_json()
    restored = GoalLifecycleSnapshot.from_json(payload).restore()
    assert restored.snapshot() == ledger.snapshot()
    assert [event.event_id for event in restored.snapshot()] == [
        "z-first", "a-second", "m-third"
    ]

def test_repeated_abandon_reopen_cycle_gets_distinct_event_ids():
    from simreality.goals import GoalStatus
    from simreality.npc_goal_emergence import GoalLifecycleLedger

    goal = NPCGoal("g", "npc", "safety", 2.0)
    ledger = GoalLifecycleLedger()
    ledger.record(goal, 1, "adopted")
    goal.status = GoalStatus.ABANDONED
    first = ledger.record(goal, 2, "conditions improved")
    goal.status = GoalStatus.ACTIVE
    ledger.record(goal, 3, "new danger")
    goal.status = GoalStatus.ABANDONED
    second = ledger.record(goal, 4, "conditions improved")
    assert first.event_id != second.event_id
    assert len(ledger.snapshot()) == 4

def test_matching_rules_do_not_emit_duplicate_goal_templates():
    goals = GoalBook()
    template = GoalTemplate("safety-plan", "safety", 4.0)
    rules = (
        GoalEmergenceRule("rule-a", template, need_key="safety", need_threshold=0.5),
        GoalEmergenceRule("rule-b", template, emotion_axis="fear", emotion_threshold=0.5),
    )
    emotions = NPCEmotionalState("npc", 2, {"fear": 0.8})
    proposals = NPCGoalEmergence.propose(
        goals, "npc", 2, rules=rules,
        need_deficits={"safety": 0.8}, emotional_state=emotions,
    )
    assert len(proposals) == 1
    assert proposals[0].rule_id == "rule-a"

def test_atomic_goal_lifecycle_transition_updates_goal_and_is_idempotent():
    from simreality.goals import GoalStatus
    from simreality.npc_goal_emergence import GoalLifecycleLedger

    goals = GoalBook()
    goal = NPCGoal("g", "npc", "safety", 2.0)
    goals.add(goal)
    ledger = GoalLifecycleLedger()
    abandoned = ledger.transition(
        goals, "g", GoalStatus.ABANDONED, 4, "risk passed")
    assert goal.status == GoalStatus.ABANDONED
    assert ledger.status_for("g") == "abandoned"
    assert ledger.transition(
        goals, "g", GoalStatus.ABANDONED, 4, "risk passed") == abandoned
    reopened = ledger.transition(
        goals, "g", GoalStatus.ACTIVE, 5, "risk returned")
    assert goal.status == GoalStatus.ACTIVE
    assert goal.review_tick == 5
    assert reopened.from_status == "abandoned"
    assert len(ledger.snapshot()) == 3  # initialization, abandonment, reopening
