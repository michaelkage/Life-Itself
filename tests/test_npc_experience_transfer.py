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


def test_strategic_retrieval_weights_personal_witnessed_and_reported_evidence():
    from simreality.npc_life_history import AutobiographicalMemory
    from simreality.npc_experience_transfer import strategic_experience_evidence

    events = WorldEventLedger((
        WorldEventLedger.make_event("direct", 2, "work", participants=("alice", "bob")),
        WorldEventLedger.make_event("witnessed", 3, "accident", witnesses=("bob",)),
        WorldEventLedger.make_event("conversation", 9, "conversation",
                                    participants=("alice", "bob")),
    ))
    history = NPCLifeHistory((
        AutobiographicalMemory("direct-memory", "bob", "direct", 2, (),
                               "I performed the repair", 0.2, 0.1),
        AutobiographicalMemory("witness-memory", "bob", "witnessed", 3, (),
                               "I watched a repair fail", 0.3, 0.1),
        AutobiographicalMemory("alice-memory", "alice", "direct", 2, (),
                               "I performed the repair", 0.2, 0.1),
    ))
    transfers = NPCExperienceTransferLedger(events, history)
    transfers.transfer("reported-share", "bob", "alice", "alice-memory",
                       "conversation", confidence=0.8)
    evidence = strategic_experience_evidence(history, transfers, "bob", 9)
    by_class = {item.source_class: item for item in evidence}
    assert by_class["personal"].influence == 1.0
    assert by_class["witnessed"].influence == 0.6
    assert by_class["reported"].influence == pytest.approx(0.28)
    assert by_class["reported"].confidence == 0.8


def test_strategic_retrieval_excludes_future_and_is_bounded_and_stable():
    from simreality.npc_experience_transfer import strategic_experience_evidence
    events, history = setup()
    transfers = NPCExperienceTransferLedger(events, history)
    first = strategic_experience_evidence(history, transfers, "alice", 4, limit=1)
    second = strategic_experience_evidence(history, transfers, "alice", 4, limit=1)
    assert first == second
    assert len(first) == 1
    assert first[0].evidence_id == "memory-alice"
    assert strategic_experience_evidence(history, transfers, "alice", 3) == ()
