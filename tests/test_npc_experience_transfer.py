import pytest
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.npc_experience_transfer import ExperienceTransferSnapshot, NPCExperienceTransferLedger
from simreality.world_events import WorldEventLedger


def setup():
    events = WorldEventLedger((
        WorldEventLedger.make_event("experience", 4, "workplace_accident",
                                    participants=("alice",), witnesses=("cara",)),
        WorldEventLedger.make_event("conversation", 9, "conversation",
                                    participants=("alice", "bob")),
    ))
    history = NPCLifeHistory((AutobiographicalMemory(
        "memory-alice", "alice", "experience", 4, ("cara",),
        "I saw the machine fail after maintenance was skipped", 0.7, 0.1,
        tags=("work", "safety")),))
    return events, history


def test_transfer_preserves_reported_provenance_not_personal_memory():
    events, history = setup()
    ledger = NPCExperienceTransferLedger(events, history)
    record = ledger.transfer("share-1", "bob", "alice", "memory-alice",
                             "conversation", confidence=0.65)
    assert record.source_role == "participant"
    assert record.source_event_id == "experience"
    assert record.communication_event_id == "conversation"
    assert record.confidence == 0.65
    assert history.memories("bob") == ()
    assert ledger.received_by("bob") == (record,)


def test_transfer_is_idempotent_and_conflicting_reuse_rejected():
    events, history = setup()
    ledger = NPCExperienceTransferLedger(events, history)
    first = ledger.transfer("share-1", "bob", "alice", "memory-alice", "conversation", confidence=0.6)
    assert ledger.transfer("share-1", "bob", "alice", "memory-alice", "conversation", confidence=0.6) is first
    with pytest.raises(ValueError, match="different content"):
        ledger.transfer("share-1", "bob", "alice", "memory-alice", "conversation", confidence=0.8)


def test_communication_must_include_both_people():
    events, history = setup()
    events.append(WorldEventLedger.make_event("unrelated", 10, "conversation",
                                               participants=("alice", "cara")))
    ledger = NPCExperienceTransferLedger(events, history)
    with pytest.raises(ValueError, match="must include source and recipient"):
        ledger.transfer("share-2", "bob", "alice", "memory-alice", "unrelated", confidence=0.5)


def test_future_event_cannot_be_shared_before_it_occurs():
    events, history = setup()
    events.append(WorldEventLedger.make_event("early-chat", 3, "conversation",
                                               participants=("alice", "bob")))
    ledger = NPCExperienceTransferLedger(events, history)
    with pytest.raises(ValueError, match="cannot precede"):
        ledger.transfer("share-3", "bob", "alice", "memory-alice", "early-chat", confidence=0.5)


def test_snapshot_roundtrip_revalidates_evidence():
    events, history = setup()
    ledger = NPCExperienceTransferLedger(events, history)
    ledger.transfer("share-1", "bob", "alice", "memory-alice", "conversation", confidence=0.65)
    snapshot = ledger.snapshot()
    encoded = snapshot.to_json()
    restored = NPCExperienceTransferLedger(events, history, ExperienceTransferSnapshot.from_json(encoded))
    assert restored.snapshot() == snapshot


def test_same_source_memory_cannot_be_resent_in_one_communication():
    events, history = setup()
    ledger = NPCExperienceTransferLedger(events, history)
    ledger.transfer("share-1", "bob", "alice", "memory-alice", "conversation", confidence=0.65)
    with pytest.raises(ValueError, match="already been transferred"):
        ledger.transfer("share-2", "bob", "alice", "memory-alice", "conversation", confidence=0.65)
