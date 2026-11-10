import pytest

from simreality.npc_life_history import (
    AutobiographicalMemory, LifeHistorySnapshot, NPCLifeHistory,
)


def memory(**overrides):
    values = dict(memory_id="m1", owner_id="alice", event_id="e1", tick=4,
                  involved_npc_ids=("bob",), interpretation="Bob betrayed my trust",
                  emotional_impact=0.9, identity_impact=-0.2,
                  conflict_ids=("c1",), learning_decision_ids=("l1",),
                  turning_point=True, tags=("betrayal",))
    values.update(overrides)
    return AutobiographicalMemory(**values)


def test_observer_owned_memories_allow_different_interpretations_of_same_event():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    ledger.record(memory(memory_id="m2", owner_id="bob", involved_npc_ids=("alice",),
                         interpretation="I was protecting myself", emotional_impact=0.2))
    assert ledger.memories("alice")[0].interpretation != ledger.memories("bob")[0].interpretation


def test_forgiveness_preserves_memory_and_does_not_imply_reconciliation():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    ledger.act("a1", "alice", "bob", "e1", action="forgive", tick=8,
               rationale="I no longer want revenge")
    state = ledger.relationship_history("alice", "bob", "e1")
    assert state["forgiven"] is True
    assert state["reconciled"] is False
    assert ledger.memories("alice")[0].interpretation == "Bob betrayed my trust"


def test_reconciliation_and_forgiveness_are_independent_choices():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    ledger.act("a1", "alice", "bob", "e1", action="reconcile", tick=7)
    state = ledger.relationship_history("alice", "bob", "e1")
    assert state["reconciled"] is True
    assert state["forgiven"] is False
    ledger.act("a2", "alice", "bob", "e1", action="forgive", tick=8)
    state = ledger.relationship_history("alice", "bob", "e1")
    assert state["reconciled"] is True
    assert state["forgiven"] is True


def test_turning_point_recall_salience_does_not_decay_and_ordinary_memory_is_retained():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    ledger.record(memory(memory_id="m2", turning_point=False, tick=0))
    assert ledger.recall_salience("m1", 1000, half_life_ticks=10) == 1
    assert ledger.recall_salience("m2", 10, half_life_ticks=10) == pytest.approx(0.5)
    assert len(ledger.memories("alice")) == 2


def test_memory_and_action_replay_are_idempotent_and_conflicts_rejected():
    ledger = NPCLifeHistory()
    item = memory()
    assert ledger.record(item) == ledger.record(item)
    with pytest.raises(ValueError):
        ledger.record(memory(interpretation="different"))
    action = ledger.act("a1", "alice", "bob", "e1", action="forgive", tick=8)
    assert ledger.act("a1", "alice", "bob", "e1", action="forgive", tick=8) == action
    with pytest.raises(ValueError):
        ledger.act("a1", "alice", "bob", "e1", action="forgive", tick=9)


def test_snapshot_round_trip_is_canonical_and_preserves_actions():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    ledger.act("a1", "alice", "bob", "e1", action="forgive", tick=8)
    payload = ledger.snapshot().to_json()
    restored = LifeHistorySnapshot.from_json(payload).restore()
    assert restored.snapshot().to_json() == payload
    assert restored.relationship_history("alice", "bob", "e1")["forgiven"]


def test_invalid_history_owner_or_future_action_is_rejected():
    ledger = NPCLifeHistory()
    ledger.record(memory())
    with pytest.raises(ValueError):
        ledger.act("a1", "mallory", "bob", "e1", action="forgive", tick=8)
    with pytest.raises(ValueError):
        ledger.act("a2", "alice", "bob", "e1", action="forgive", tick=3)
