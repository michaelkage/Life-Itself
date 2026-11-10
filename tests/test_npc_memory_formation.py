import pytest

from simreality.npc_life_history import NPCLifeHistory
from simreality.npc_memory_formation import (
    AutobiographicalMemoryProfile, AutobiographicalMemoryRule,
    NPCAutobiographicalMemoryAdapter,
)
from simreality.world_events import WorldEventLedger


def profile(owner, role, interpretation, *, rule_id="r1", event_type="betrayal",
            emotional=0.8, identity=-0.2, turning=False):
    return AutobiographicalMemoryProfile(owner, (
        AutobiographicalMemoryRule(
            rule_id, event_type, role, interpretation, emotional, identity,
            turning_point=turning, tags=("relationship",),
            include_participants=True, include_witnesses=True,
        ),
    ))


def test_same_event_forms_distinct_observer_interpretations():
    event = WorldEventLedger.make_event(
        "e1", 10, "betrayal", participants=("alice", "bob"), witnesses=("cara",),
    )
    history = NPCLifeHistory()
    formed = NPCAutobiographicalMemoryAdapter.process(
        (event,), {
            "alice": profile("alice", "participant", "Bob abandoned me"),
            "bob": profile("bob", "participant", "I had no choice"),
            "cara": profile("cara", "witness", "I saw a friendship break"),
        }, history,
    )
    assert len(formed) == 3
    assert {m.owner_id: m.interpretation for m in formed} == {
        "alice": "Bob abandoned me", "bob": "I had no choice",
        "cara": "I saw a friendship break",
    }


def test_memory_formation_is_idempotent_and_rule_changes_conflict():
    event = WorldEventLedger.make_event("e1", 2, "loss", participants=("alice",))
    history = NPCLifeHistory()
    profiles = {"alice": profile("alice", "participant", "I lost someone")}
    first = NPCAutobiographicalMemoryAdapter.process((event,), profiles, history)
    second = NPCAutobiographicalMemoryAdapter.process((event,), profiles, history)
    assert first == second
    assert len(history.memories("alice")) == 1
    changed = {"alice": profile("alice", "participant", "A different account")}
    with pytest.raises(ValueError, match="reused with different content"):
        NPCAutobiographicalMemoryAdapter.process((event,), changed, history)


def test_linked_conflicts_and_learning_decisions_are_preserved():
    event = WorldEventLedger.make_event("e1", 3, "assault", participants=("alice", "bob"))
    history = NPCLifeHistory()
    formed = NPCAutobiographicalMemoryAdapter.process(
        (event,), {"alice": profile("alice", "participant", "I was attacked")},
        history,
        conflict_ids_by_event_observer={("e1", "alice"): ("c1",)},
        learning_decision_ids_by_event_observer={("e1", "alice"): ("d1",)},
    )
    assert formed[0].conflict_ids == ("c1",)
    assert formed[0].learning_decision_ids == ("d1",)


def test_unobserved_npcs_do_not_form_memories_and_rule_role_is_respected():
    event = WorldEventLedger.make_event("e1", 1, "argument", participants=("alice",))
    history = NPCLifeHistory()
    formed = NPCAutobiographicalMemoryAdapter.process(
        (event,), {"bob": profile("bob", "witness", "I heard it")},
        history,
    )
    assert formed == ()
    assert history.memories() == ()


def test_invalid_linked_reference_shape_is_rejected_by_memory_contract():
    event = WorldEventLedger.make_event("e1", 1, "argument", participants=("alice",))
    history = NPCLifeHistory()
    with pytest.raises(ValueError, match="tuple of non-empty strings"):
        NPCAutobiographicalMemoryAdapter.process(
            (event,), {"alice": profile("alice", "participant", "I was there")},
            history, conflict_ids_by_event_observer={("e1", "alice"): ("",)},
        )
