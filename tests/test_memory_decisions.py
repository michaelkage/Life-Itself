import pytest

from simreality.npc_life_history import AutobiographicalMemory
from simreality.npc_memory_recall import MemoryRecallResult, RecalledMemory
from simreality.memory_decisions import (
    MemoryChoiceAssociation, MemoryDecisionInfluenceAdapter, MemoryDecisionProfile,
)


def recalled(memory_id, score, owner="alice"):
    memory = AutobiographicalMemory(
        memory_id, owner, "event-" + memory_id, 0, (), "meaning",
        0.5, 0.0,
    )
    return RecalledMemory(memory, score, ("cue",), ("rule",))


def test_explicit_signed_associations_translate_recall_into_choice_signals():
    result = MemoryRecallResult("alice", 10, (
        recalled("m1", 0.8), recalled("m2", 0.5),
    ))
    profile = MemoryDecisionProfile("alice", (
        MemoryChoiceAssociation("a1", "alice", "m1", "approach", 0.75),
        MemoryChoiceAssociation("a2", "alice", "m2", "approach", -0.5),
        MemoryChoiceAssociation("a3", "alice", "m1", "avoid", -1.0),
    ))
    influence = MemoryDecisionInfluenceAdapter.evaluate(profile, result)
    assert influence.contributions_for("approach") == (
        ("m1", 0.6), ("m2", -0.25),
    )
    assert influence.contributions_for("avoid") == (("m1", -0.8),)


def test_accumulated_contributions_are_bounded_to_prevent_memory_dominance():
    result = MemoryRecallResult("alice", 2, (
        recalled("m1", 1.0), recalled("m2", 1.0),
    ))
    profile = MemoryDecisionProfile("alice", (
        MemoryChoiceAssociation("a1", "alice", "m1", "choice", 1.0),
        MemoryChoiceAssociation("a2", "alice", "m2", "choice", 1.0),
    ))
    values = influence = MemoryDecisionInfluenceAdapter.evaluate(profile, result)
    assert sum(value for _, value in influence.contributions_for("choice")) == pytest.approx(1.0)


def test_unrecalled_memories_do_not_influence_choices():
    result = MemoryRecallResult("alice", 2, (recalled("m1", 0.8),))
    profile = MemoryDecisionProfile("alice", (
        MemoryChoiceAssociation("a1", "alice", "m2", "choice", 1.0),
    ))
    assert MemoryDecisionInfluenceAdapter.evaluate(profile, result).choice_contributions == ()


def test_cross_owner_and_duplicate_associations_are_rejected():
    with pytest.raises(ValueError):
        MemoryDecisionProfile("alice", (
            MemoryChoiceAssociation("a1", "bob", "m1", "choice", 1.0),
        ))
    with pytest.raises(ValueError):
        MemoryDecisionProfile("alice", (
            MemoryChoiceAssociation("a1", "alice", "m1", "choice", 1.0),
            MemoryChoiceAssociation("a2", "alice", "m1", "choice", -1.0),
        ))
    with pytest.raises(ValueError):
        MemoryDecisionInfluenceAdapter.evaluate(
            MemoryDecisionProfile("alice", ()),
            MemoryRecallResult("bob", 1, ()),
        )
