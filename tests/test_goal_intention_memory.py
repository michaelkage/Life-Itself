import pytest

from simreality.action_evaluation import ActionPlanEvaluationLedger
from simreality.goal_arbitration import GoalCommitment, GoalCommitmentLedger
from simreality.goals import GoalBook, NPCGoal
from simreality.npc_goal_emergence import GoalLifecycleEvent, GoalLifecycleLedger
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.goal_intention_memory import (
    GoalIntentionMemory, GoalIntentionMemoryAdapter,
    GoalIntentionMemoryLedger, GoalIntentionMemorySnapshot,
)


def goal_book():
    goals = GoalBook()
    goals.add(NPCGoal("g1", "alice", "survival", 0.8))
    goals.add(NPCGoal("g2", "alice", "family", 0.7))
    return goals


def test_lifecycle_commitment_and_personal_evidence_form_provenance_linked_memory():
    goals = goal_book()
    lifecycle = GoalLifecycleLedger((
        GoalLifecycleEvent("life-1", "g1", "alice", None, "active", 2,
                           "Adopted to secure food", ("m1",)),
    ))
    history = NPCLifeHistory((
        AutobiographicalMemory("m1", "alice", "event-1", 1, ("bob",),
                              "I promised to protect my family", 0.8, 0.2),
    ))
    commitment = GoalCommitment(
        "commit-1", "a" * 64, "alice", 3, "g1", ("g2",), 0.9,
        "Immediate danger outweighs other ambitions",
    )
    commitments = GoalCommitmentLedger((commitment,))
    ledger = GoalIntentionMemoryLedger()
    created = GoalIntentionMemoryAdapter.ingest(
        ledger, goals=goals, current_tick=3, lifecycle=lifecycle,
        commitments=commitments, life_history=history,
    )
    assert {item.memory_type for item in created} == {
        "adopted", "personal_experience", "committed", "deferred",
    }
    personal = next(item for item in created if item.memory_type == "personal_experience")
    assert personal.content == "I promised to protect my family"
    assert personal.evidence_ids == ("event-1", "m1")
    assert next(item for item in created if item.memory_type == "committed").content == commitment.rationale


def test_ingestion_is_idempotent_and_rejects_conflicting_source_reuse():
    ledger = GoalIntentionMemoryLedger()
    item = ledger.make("alice", "g1", 1, "adopted", "goal_lifecycle",
                       "life-1", "Adopted", ())
    assert ledger.record(item) == ledger.record(item)
    changed = GoalIntentionMemory(
        item.memory_id, item.owner_id, item.goal_id, item.tick, item.memory_type,
        item.source_kind, item.source_id, "Changed", (),
    )
    with pytest.raises(ValueError):
        ledger.record(changed)


def test_memory_snapshot_is_canonical_and_restorable():
    ledger = GoalIntentionMemoryLedger()
    ledger.record(ledger.make("alice", "g1", 1, "adopted", "goal_lifecycle",
                              "life-1", "Adopted", ()))
    payload = ledger.snapshot().to_json()
    restored = GoalIntentionMemorySnapshot.from_json(payload).restore()
    assert restored.snapshot().to_json() == payload


def test_goal_memory_rejects_bad_identity_and_future_source():
    with pytest.raises(ValueError):
        GoalIntentionMemory("wrong", "alice", "g1", 1, "adopted",
                            "goal_lifecycle", "life-1", "Adopted")
    goals = goal_book()
    lifecycle = GoalLifecycleLedger((
        GoalLifecycleEvent("life-1", "g1", "alice", None, "active", 4,
                           "Adopted"),
    ))
    with pytest.raises(ValueError):
        GoalIntentionMemoryAdapter.ingest(
            GoalIntentionMemoryLedger(), goals=goals, current_tick=3,
            lifecycle=lifecycle,
        )
