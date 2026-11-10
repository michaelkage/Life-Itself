import pytest

from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.npc_memory_recall import (
    MemoryRecallProfile, MemoryRecallRule, NPCMemoryRecallAdapter,
)


def make_memory(memory_id, owner="alice", tick=0, tags=("fire",), involved=("bob",),
                emotional=0.5, turning=False):
    return AutobiographicalMemory(
        memory_id, owner, "event-" + memory_id, tick, involved,
        "A personal interpretation", emotional, 0.0, turning_point=turning, tags=tags,
    )


def test_cues_recall_only_matching_owner_memories_and_rank_by_salience():
    history = NPCLifeHistory((
        make_memory("old", tick=0),
        make_memory("recent", tick=9),
        make_memory("other", owner="bob", tick=10),
        make_memory("unmatched", tags=("water",), tick=10),
    ))
    profile = MemoryRecallProfile("alice", (
        MemoryRecallRule("fire-tag", "smoke", tag="fire"),
    ))
    result = NPCMemoryRecallAdapter.recall(
        profile, history, {"smoke": 1.0}, 10,
        half_life_ticks=10, top_k=5,
    )
    assert [item.memory.memory_id for item in result.recalled] == ["recent", "old"]
    assert result.recalled[0].score > result.recalled[1].score
    assert all(item.memory.owner_id == "alice" for item in result.recalled)


def test_person_association_and_emotional_weight_are_explicit():
    history = NPCLifeHistory((
        make_memory("m1", involved=("bob",), emotional=0.8),
        make_memory("m2", involved=("cara",), emotional=0.8),
    ))
    profile = MemoryRecallProfile("alice", (
        MemoryRecallRule("bob-rule", "bob-seen", involved_npc_id="bob"),
    ), emotional_weight=0.5)
    result = NPCMemoryRecallAdapter.recall(
        profile, history, {"bob-seen": 0.7}, 0,
        half_life_ticks=10,
    )
    assert [item.memory.memory_id for item in result.recalled] == ["m1"]
    assert result.recalled[0].score == pytest.approx(0.7 * 1.4)


def test_turning_point_stays_salient_and_threshold_and_top_k_are_applied():
    history = NPCLifeHistory((
        make_memory("ordinary", tick=0),
        make_memory("turning", tick=0, turning=True),
    ))
    profile = MemoryRecallProfile("alice", (
        MemoryRecallRule("rule", "cue", tag="fire"),
    ))
    result = NPCMemoryRecallAdapter.recall(
        profile, history, {"cue": 1.0}, 100,
        half_life_ticks=10, minimum_score=0.5, top_k=1,
    )
    assert len(result.recalled) == 1
    assert result.recalled[0].memory.memory_id == "turning"
    assert result.recalled[0].score == 1.0


def test_recall_is_read_only_and_deterministic():
    history = NPCLifeHistory((make_memory("m1"),))
    before = history.snapshot().to_json()
    profile = MemoryRecallProfile("alice", (
        MemoryRecallRule("rule", "cue", tag="fire"),
    ))
    args = (profile, history, {"cue": 0.6}, 4)
    first = NPCMemoryRecallAdapter.recall(*args, half_life_ticks=10)
    second = NPCMemoryRecallAdapter.recall(*args, half_life_ticks=10)
    assert first == second
    assert history.snapshot().to_json() == before


def test_invalid_profiles_and_recall_limits_are_rejected():
    with pytest.raises(ValueError):
        MemoryRecallRule("empty", "cue")
    with pytest.raises(ValueError):
        MemoryRecallProfile("alice", (), emotional_weight=1.1)
    profile = MemoryRecallProfile("alice", ())
    with pytest.raises(ValueError):
        NPCMemoryRecallAdapter.recall(
            profile, NPCLifeHistory(), {"cue": 1.0}, 0,
            half_life_ticks=10, top_k=0,
        )
