import pytest

from simreality.emotional_memory import (
    EmotionalMemoryAdapter, EmotionalMemoryAssociation, EmotionalMemoryProfile,
)
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory


def make_history():
    history = NPCLifeHistory()
    history.record(AutobiographicalMemory(
        "memory-fire", "alice", "event-fire", 0, ("bob",),
        "The house burned while Bob was inside", 0.8, 0.9,
        tags=("loss", "fear"),
    ))
    history.record(AutobiographicalMemory(
        "memory-reunion", "alice", "event-reunion", 5, ("bob",),
        "Bob returned safely", 0.7, 0.6,
        tags=("relief",),
    ))
    return history


def test_distinct_memories_can_trigger_coexisting_emotions():
    history = make_history()
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("fire-smell", "memory-fire", "smoke-smell", "fear"),
        EmotionalMemoryAssociation("bob-presence", "memory-fire", "bob-nearby", "resentment", 0.5),
        EmotionalMemoryAssociation("bob-return", "memory-reunion", "bob-nearby", "affection"),
    ))
    result = EmotionalMemoryAdapter.evaluate(
        history, profile, {"smoke-smell": 1.0, "bob-nearby": 1.0}, 5,
        half_life_ticks=100.0,
    )
    intensities = dict(result.intensities)
    assert intensities["fear"] > 0
    assert intensities["resentment"] > 0
    assert intensities["affection"] > 0
    assert len(result.contributions) == 3


def test_emotional_memory_is_read_only_and_deterministic():
    history = make_history()
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("cue-1", "memory-fire", "sirens", "fear"),
    ))
    before = history.snapshot().to_json()
    first = EmotionalMemoryAdapter.evaluate(history, profile, {"sirens": 0.75}, 10)
    second = EmotionalMemoryAdapter.evaluate(history, profile, {"sirens": 0.75}, 10)
    assert first == second
    assert history.snapshot().to_json() == before


def test_unknown_memory_owner_and_future_memory_are_rejected():
    history = make_history()
    wrong_owner = EmotionalMemoryProfile("bob", (
        EmotionalMemoryAssociation("cue-1", "memory-fire", "sirens", "fear"),
    ))
    with pytest.raises(KeyError, match="not owned"):
        EmotionalMemoryAdapter.evaluate(history, wrong_owner, {"sirens": 1.0}, 10)

    future_history = NPCLifeHistory((
        AutobiographicalMemory(
            "future", "alice", "event-future", 12, (),
            "A future memory", 0.5, 0.5,
        ),
    ))
    future_profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("cue-2", "future", "future-cue", "hope"),
    ))
    with pytest.raises(ValueError, match="future tick"):
        EmotionalMemoryAdapter.evaluate(
            future_history, future_profile, {"future-cue": 1.0}, 10,
        )


def test_exposure_and_decay_bound_the_response():
    history = make_history()
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("cue-1", "memory-fire", "smoke", "fear"),
    ))
    result = EmotionalMemoryAdapter.evaluate(
        history, profile, {"smoke": 0.25}, 100,
        half_life_ticks=100.0,
    )
    assert dict(result.intensities)["fear"] == pytest.approx(0.9 * 0.25 * 0.5)
    assert all(0.0 <= value <= 1.0 for _, value in result.intensities)


def test_invalid_or_duplicate_associations_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        EmotionalMemoryProfile("alice", (
            EmotionalMemoryAssociation("same", "memory-fire", "smoke", "fear"),
            EmotionalMemoryAssociation("same", "memory-fire", "smoke", "fear"),
        ))
    with pytest.raises(ValueError, match="sensitivity"):
        EmotionalMemoryAssociation("bad", "memory-fire", "smoke", "fear", 1.5)
