"""Tagged autobiographical experience influences future NPC action proposals."""
from simreality.action_execution import ActionExecutionLedger
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_action_replanning import NPCActionReplanningCoordinator
from simreality.npc_autonomy import NPCDecisionCycle
from simreality.npc_experience_transfer import NPCExperienceTransferLedger
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger


def setup():
    events = WorldEventLedger((
        WorldEventLedger.make_event("repair-failed", 1, "repair_attempt",
                                    participants=("alice",)),
        WorldEventLedger.make_event("conversation", 2, "conversation",
                                    participants=("alice", "bob")),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "alice-repair-memory", "alice", "repair-failed", 1, (),
        "The repair failed", 0.4, 0.1,
        tags=("repair", "outcome:failure")),))
    transfers = NPCExperienceTransferLedger(events, history)
    transfers.transfer("repair-report", "bob", "alice", "alice-repair-memory",
                       "conversation", confidence=1.0)
    planner = DeterministicPlanner((
        PlanningAction("a-safe-route", frozenset({"start"}), frozenset({"done"}), cost=6),
        PlanningAction("z-repair-route", frozenset({"start"}), frozenset({"done"}),
                       cost=3, experience_tags=("repair",)),
    ))
    return events, history, transfers, planner


def coordinator(owner, events, history, transfers, planner):
    goals = GoalBook()
    goals.add(NPCGoal("goal", owner, "maintenance", 5.0))
    executions = ActionExecutionLedger(planner, (), events)
    decisions = NPCDecisionCycle(goals, planner)
    return NPCActionReplanningCoordinator(
        decisions, executions, events, life_history=history,
        experience_transfers=transfers,
    )


def test_personal_failure_outweighs_reported_failure_in_action_choice():
    events, history, transfers, planner = setup()
    personal = coordinator("alice", events, history, transfers, planner)
    reported = coordinator("bob", events, history, transfers, planner)
    personal_result = personal.replan("alice", 2, {"start"}, {},
                                      {"goal": {"done"}}, reason="personal learning")
    reported_result = reported.replan("bob", 2, {"start"}, {},
                                      {"goal": {"done"}}, reason="reported learning")
    assert personal_result.action_id == "a-safe-route"
    assert reported_result.action_id == "z-repair-route"
    assert personal_result.decision.experience_evidence_ids == ("alice-repair-memory",)
    assert personal_result.decision.experience_evidence_sources == (("alice-repair-memory", "personal"),)
    assert reported_result.decision.experience_evidence_ids == ("repair-report",)
    assert reported_result.decision.experience_evidence_sources == (("repair-report", "reported"),)


def test_unmatched_or_unclassified_memory_does_not_change_action_choice():
    events = WorldEventLedger((
        WorldEventLedger.make_event("memory-event", 1, "ordinary_event",
                                    participants=("npc",)),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "unrelated-memory", "npc", "memory-event", 1, (),
        "An unrelated event", 0.2, 0.0, tags=("cooking",)),))
    transfers = NPCExperienceTransferLedger(events, history)
    planner = DeterministicPlanner((
        PlanningAction("a-first", frozenset({"start"}), frozenset({"done"}), cost=1),
        PlanningAction("z-tagged", frozenset({"start"}), frozenset({"done"}),
                       cost=1, experience_tags=("repair",)),
    ))
    result = coordinator("npc", events, history, transfers, planner).replan(
        "npc", 1, {"start"}, {}, {"goal": {"done"}}, reason="unrelated memory")
    assert result.action_id == "a-first"
    assert result.decision.experience_evidence_ids == ()


def test_replanning_snapshot_preserves_experience_attribution():
    events, history, transfers, planner = setup()
    original = coordinator("bob", events, history, transfers, planner)
    result = original.replan("bob", 2, {"start"}, {},
                             {"goal": {"done"}}, reason="persist experience")
    restored = NPCActionReplanningCoordinator.from_snapshot(
        original.decisions, original.executions, events, original.to_snapshot(),
        life_history=history, experience_transfers=transfers,
    )
    replay = restored.replan("bob", 2, {"start"}, {},
                             {"goal": {"done"}}, reason="persist experience")
    assert replay == result
    assert replay.decision.experience_evidence_ids == ("repair-report",)
    assert replay.decision.experience_evidence_sources == (("repair-report", "reported"),)


def test_reported_goal_outcome_adjusts_future_goal_ranking_without_mutating_priority():
    from simreality.npc_experience_transfer import experience_goal_guidance

    events = WorldEventLedger((
        WorldEventLedger.make_event("rescue-event", 1, "goal_outcome",
                                    participants=("alice",)),
        WorldEventLedger.make_event("goal-conversation", 2, "conversation",
                                    participants=("alice", "bob")),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "rescue-memory", "alice", "rescue-event", 1, (),
        "The rescue goal succeeded", 0.8, 0.1,
        tags=("rescue", "goal:success")),))
    transfers = NPCExperienceTransferLedger(events, history)
    transfers.transfer("rescue-report", "bob", "alice", "rescue-memory",
                       "goal-conversation", confidence=1.0)

    goals = GoalBook()
    goals.add(NPCGoal("rescue-goal", "bob", "rescue", 3.9,
                      metadata={"experience_tags": "rescue"}))
    goals.add(NPCGoal("routine-goal", "bob", "routine", 4.0))
    base_priority = goals.goals["rescue-goal"].priority

    adjustments, evidence_ids, sources = experience_goal_guidance(
        history, transfers, "bob", 2, goals)
    assert adjustments["rescue-goal"] > 0
    assert evidence_ids["rescue-goal"] == ("rescue-report",)
    assert sources["rescue-report"] == "reported"

    planner = DeterministicPlanner((
        PlanningAction("complete-either", frozenset({"start"}),
                       frozenset({"rescue-done", "routine-done"})),
    ))
    decision = NPCDecisionCycle(goals, planner).decide(
        "bob", 2, {"start"},
        {"rescue-goal": {"rescue-done"}, "routine-goal": {"routine-done"}},
        goal_experience_adjustments=adjustments,
    )
    assert decision.goal_id == "rescue-goal"
    assert goals.goals["rescue-goal"].priority == base_priority


def test_action_outcome_memory_does_not_change_goal_priority():
    from simreality.npc_experience_transfer import experience_goal_guidance

    events = WorldEventLedger((
        WorldEventLedger.make_event("action-event", 1, "action_outcome",
                                    participants=("npc",)),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "action-memory", "npc", "action-event", 1, (),
        "A repair action succeeded", 0.8, 0.1,
        tags=("repair", "outcome:success")),))
    transfers = NPCExperienceTransferLedger(events, history)
    goals = GoalBook()
    goals.add(NPCGoal("repair-goal", "npc", "repair", 5.0,
                      metadata={"experience_tags": "repair"}))
    adjustments, evidence_ids, _ = experience_goal_guidance(
        history, transfers, "npc", 1, goals)
    assert adjustments == {}
    assert evidence_ids == {}


def test_replanning_uses_goal_experience_to_select_between_goals():
    events = WorldEventLedger((
        WorldEventLedger.make_event("community-event", 1, "goal_outcome",
                                    participants=("alice",)),
        WorldEventLedger.make_event("community-chat", 2, "conversation",
                                    participants=("alice", "bob")),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "community-memory", "alice", "community-event", 1, (),
        "The community project succeeded", 0.9, 0.1,
        tags=("community", "goal:success")),))
    transfers = NPCExperienceTransferLedger(events, history)
    transfers.transfer("community-report", "bob", "alice", "community-memory",
                       "community-chat", confidence=1.0)
    planner = DeterministicPlanner((
        PlanningAction("do-goal", frozenset({"start"}),
                       frozenset({"community-done", "routine-done"})),
    ))
    goals = GoalBook()
    goals.add(NPCGoal("community-goal", "bob", "community", 3.9,
                      metadata={"experience_tags": "community"}))
    goals.add(NPCGoal("routine-goal", "bob", "routine", 4.0))
    executions = ActionExecutionLedger(planner, (), events)
    decisions = NPCDecisionCycle(goals, planner)
    replanning = NPCActionReplanningCoordinator(
        decisions, executions, events,
        life_history=history, experience_transfers=transfers,
    )
    result = replanning.replan(
        "bob", 2, {"start"}, {},
        {"community-goal": {"community-done"},
         "routine-goal": {"routine-done"}},
        reason="apply reported strategic experience",
    )
    assert result.decision.goal_id == "community-goal"
    assert result.decision.experience_evidence_ids == ("community-report",)
    assert result.decision.experience_evidence_sources == (("community-report", "reported"),)
