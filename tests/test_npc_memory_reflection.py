import pytest

from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.npc_memory_reflection import (
    MemoryReflectionLedger, MemoryReflectionSnapshot, MemoryReinterpretation,
)


def setup():
    history = NPCLifeHistory((
        AutobiographicalMemory(
            "memory-1", "alice", "event-1", 2, ("bob",),
            "Bob abandoned me", 0.8, -0.2, tags=("betrayal",),
        ),
    ))
    return history


def test_reflection_changes_current_interpretation_without_rewriting_memory():
    history = setup()
    ledger = MemoryReflectionLedger(history)
    entry = MemoryReinterpretation(
        "reflection-1", "alice", "memory-1", 5,
        "Bob abandoned me", "Bob may have been afraid too",
        "I learned more about what happened that night",
    )
    ledger.record(entry)
    assert ledger.current_interpretation("alice", "memory-1") == entry.new_interpretation
    assert history.memories("alice")[0].interpretation == "Bob abandoned me"


def test_reflections_form_an_append_only_chronological_chain():
    ledger = MemoryReflectionLedger(setup())
    first = MemoryReinterpretation(
        "r1", "alice", "memory-1", 5, "Bob abandoned me",
        "I felt abandoned", "I can distinguish intent from impact",
    )
    second = MemoryReinterpretation(
        "r2", "alice", "memory-1", 9, "I felt abandoned",
        "We both made mistakes", "A later conversation changed my view",
    )
    ledger.record(first)
    ledger.record(second)
    assert ledger.current_interpretation("alice", "memory-1") == second.new_interpretation
    assert len(ledger.entries("alice", "memory-1")) == 2


def test_replay_is_idempotent_and_conflicting_or_stale_reflections_fail():
    ledger = MemoryReflectionLedger(setup())
    item = MemoryReinterpretation(
        "r1", "alice", "memory-1", 5, "Bob abandoned me",
        "I felt abandoned", "Reflection",
    )
    assert ledger.record(item) == ledger.record(item)
    with pytest.raises(ValueError):
        ledger.record(MemoryReinterpretation(
            "r1", "alice", "memory-1", 5, "Bob abandoned me",
            "Something else", "Conflicting replay",
        ))
    with pytest.raises(ValueError, match="current interpretation"):
        ledger.record(MemoryReinterpretation(
            "r2", "alice", "memory-1", 6, "Bob abandoned me",
            "New view", "Stale predecessor",
        ))


def test_reflection_cannot_cross_owner_or_precede_memory():
    ledger = MemoryReflectionLedger(setup())
    with pytest.raises(KeyError):
        ledger.record(MemoryReinterpretation(
            "r1", "mallory", "memory-1", 5, "Original", "New", "Reason",
        ))
    with pytest.raises(ValueError, match="precede"):
        ledger.record(MemoryReinterpretation(
            "r2", "alice", "memory-1", 1, "Bob abandoned me",
            "New view", "Too early",
        ))


def test_snapshot_round_trip_is_canonical_and_restores_against_history():
    history = setup()
    ledger = MemoryReflectionLedger(history)
    ledger.record(MemoryReinterpretation(
        "r1", "alice", "memory-1", 5, "Bob abandoned me",
        "I felt abandoned", "Reflection",
    ))
    payload = ledger.snapshot().to_json()
    restored = MemoryReflectionSnapshot.from_json(payload).restore(history)
    assert restored.snapshot().to_json() == payload
    assert restored.current_interpretation("alice", "memory-1") == "I felt abandoned"
