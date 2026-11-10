import pytest

from simreality.emotional_scars import EmotionalScar, NPCEmotionalScarLedger
from simreality.emotional_scars_save_state import EmotionalScarSnapshot
from simreality.emotional_memory import (
    EmotionalMemoryAdapter, EmotionalMemoryAssociation, EmotionalMemoryProfile,
)
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.emotional_scar_formation import (
    EmotionalScarDecision, EmotionalScarDecisionLedger,
    EmotionalScarDecisionSnapshot, EmotionalScarFormationAdapter,
    EmotionalScarFormationPolicy,
)


def make_scar(**overrides):
    values = dict(
        scar_id="scar-1", owner_id="alice", source_event_id="event-1",
        source_memory_id="memory-1", created_tick=2, emotion_axis="fear",
        cue_id="smoke", initial_severity=0.8, retained_per_tick=0.99,
    )
    values.update(overrides)
    return EmotionalScar(**values)


def test_scar_is_persistent_but_gradually_recovers_and_responds_to_cue():
    ledger = NPCEmotionalScarLedger()
    scar = make_scar()
    ledger.add_scar(scar)
    first = ledger.evaluate("alice", {"smoke": 1.0}, 2)
    later = ledger.evaluate("alice", {"smoke": 1.0}, 12)
    assert dict(first.intensities)["fear"] == pytest.approx(0.8)
    assert dict(later.intensities)["fear"] == pytest.approx(0.8 * 0.99 ** 10)
    assert later.contributions[0].source_memory_id == "memory-1"


def test_explicit_recovery_reduces_scar_without_erasing_its_history():
    ledger = NPCEmotionalScarLedger()
    ledger.add_scar(make_scar())
    ledger.recover(
        recovery_id="recovery-1", scar_id="scar-1", owner_id="alice",
        tick=5, amount=0.25, method="support",
    )
    assert ledger.severity_for("scar-1", 5) == pytest.approx(0.8 * 0.99 ** 3 - 0.25)
    assert len(ledger.scars("alice")) == 1
    assert len(ledger.recoveries("alice")) == 1


def test_recovery_is_owner_scoped_bounded_and_idempotent():
    ledger = NPCEmotionalScarLedger()
    ledger.add_scar(make_scar())
    kwargs = dict(
        recovery_id="recovery-1", scar_id="scar-1", owner_id="alice",
        tick=3, amount=0.2, method="counselling",
    )
    first = ledger.recover(**kwargs)
    assert ledger.recover(**kwargs) == first
    with pytest.raises(ValueError, match="owner"):
        ledger.recover(**{**kwargs, "recovery_id": "other", "owner_id": "bob"})
    with pytest.raises(ValueError, match="exceeds"):
        ledger.recover(**{**kwargs, "recovery_id": "too-much", "amount": 1.0})


def test_replay_conflicts_and_future_or_duplicate_source_are_rejected():
    ledger = NPCEmotionalScarLedger()
    scar = make_scar()
    ledger.add_scar(scar)
    assert ledger.add_scar(scar) == scar
    with pytest.raises(ValueError, match="conflicting"):
        ledger.add_scar(make_scar(initial_severity=0.7))
    with pytest.raises(ValueError, match="already created"):
        ledger.add_scar(make_scar(scar_id="scar-2"))
    with pytest.raises(ValueError, match="current_tick"):
        ledger.add_scar(make_scar(scar_id="old", created_tick=1))


def test_snapshot_round_trip_preserves_scar_and_recovery_history():
    ledger = NPCEmotionalScarLedger()
    ledger.add_scar(make_scar())
    ledger.recover(
        recovery_id="recovery-1", scar_id="scar-1", owner_id="alice",
        tick=5, amount=0.2, method="support",
    )
    ledger.current_tick = 20
    snapshot = EmotionalScarSnapshot.capture(ledger)
    restored = snapshot.restore()
    assert restored.snapshot() == ledger.snapshot()
    assert restored.severity_for("scar-1", 20) == pytest.approx(ledger.severity_for("scar-1", 20))


def test_missing_cue_is_neutral_and_future_evaluation_rejected():
    ledger = NPCEmotionalScarLedger()
    ledger.add_scar(make_scar())
    assert ledger.evaluate("alice", {"other": 1.0}, 2).intensities == ()
    with pytest.raises(ValueError, match="cannot precede"):
        ledger.evaluate("alice", {"smoke": 1.0}, 1)


def make_grounded_response():
    history = NPCLifeHistory()
    history.record(AutobiographicalMemory(
        "memory-1", "alice", "event-1", 2, ("bob",),
        "The event was frightening", 0.9, -0.2, turning_point=True,
    ))
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("association-1", "memory-1", "smoke", "fear", 1.0),
    ))
    response = EmotionalMemoryAdapter.evaluate(
        history, profile, {"smoke": 1.0}, 2,
    )
    return history, response


def test_formation_requires_grounded_evidence_and_explicit_acceptance():
    history, response = make_grounded_response()
    policy = EmotionalScarFormationPolicy(
        "high-impact", minimum_intensity=0.6, severity_scale=0.8,
    )
    proposals = EmotionalScarFormationAdapter.propose(history, response, policy)
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.source_event_id == "event-1"
    assert proposal.source_memory_id == "memory-1"
    ledger = EmotionalScarDecisionLedger()
    ledger.add_proposal(proposal)
    assert ledger.scars.scars() == ()
    decision = EmotionalScarDecision(
        "decision-1", proposal.proposal_id, "alice", 3, True,
        "I recognise this lasting response",
    )
    ledger.decide(decision)
    assert len(ledger.scars.scars("alice")) == 1
    scar = ledger.scars.scars("alice")[0]
    assert scar.source_event_id == "event-1"
    assert scar.source_memory_id == "memory-1"
    assert scar.created_tick == 3
    assert scar.initial_severity == pytest.approx(0.72)


def test_rejected_scar_proposal_is_preserved_without_creating_a_scar():
    history, response = make_grounded_response()
    proposal = EmotionalScarFormationAdapter.propose(
        history, response, EmotionalScarFormationPolicy("policy"),
    )[0]
    ledger = EmotionalScarDecisionLedger()
    ledger.add_proposal(proposal)
    rejected = EmotionalScarDecision(
        "decision-rejected", proposal.proposal_id, "alice", 3, False,
        "I do not identify with this proposed lasting imprint",
    )
    ledger.decide(rejected)
    assert ledger.decisions("alice") == (rejected,)
    assert ledger.scars.scars() == ()


def test_proposal_generation_is_deterministic_and_thresholded():
    history, response = make_grounded_response()
    policy = EmotionalScarFormationPolicy("policy", minimum_intensity=0.95)
    assert EmotionalScarFormationAdapter.propose(history, response, policy) == ()
    policy = EmotionalScarFormationPolicy("policy", minimum_intensity=0.5)
    first = EmotionalScarFormationAdapter.propose(history, response, policy)
    second = EmotionalScarFormationAdapter.propose(history, response, policy)
    assert first == second


def test_decisions_are_owner_scoped_single_use_and_replay_safe():
    history, response = make_grounded_response()
    proposal = EmotionalScarFormationAdapter.propose(
        history, response, EmotionalScarFormationPolicy("policy"),
    )[0]
    ledger = EmotionalScarDecisionLedger()
    ledger.add_proposal(proposal)
    decision = EmotionalScarDecision("decision-1", proposal.proposal_id, "alice", 3, True, "accepted")
    assert ledger.decide(decision) == decision
    assert ledger.decide(decision) == decision
    with pytest.raises(ValueError, match="owner"):
        ledger.decide(EmotionalScarDecision("decision-2", proposal.proposal_id, "bob", 4, False, "no"))
    with pytest.raises(ValueError, match="already"):
        ledger.decide(EmotionalScarDecision("decision-3", proposal.proposal_id, "alice", 4, False, "changed mind"))


def test_decision_snapshot_restores_rejections_scars_and_recovery_history():
    history, response = make_grounded_response()
    proposal = EmotionalScarFormationAdapter.propose(
        history, response, EmotionalScarFormationPolicy("policy"),
    )[0]
    ledger = EmotionalScarDecisionLedger()
    ledger.add_proposal(proposal)
    ledger.decide(EmotionalScarDecision("accepted", proposal.proposal_id, "alice", 3, True, "accepted"))
    scar = ledger.scars.scars()[0]
    ledger.scars.recover(
        recovery_id="recovery-1", scar_id=scar.scar_id, owner_id="alice",
        tick=4, amount=0.1, method="support",
    )
    snapshot = EmotionalScarDecisionSnapshot.capture(ledger)
    restored = snapshot.restore()
    assert restored.snapshot() == ledger.snapshot()
    assert restored.decisions() == ledger.decisions()
    assert restored.scars.scars() == ledger.scars.scars()
    assert restored.scars.recoveries() == ledger.scars.recoveries()


def test_decision_snapshot_preserves_recovery_before_later_scar_creation():
    history = NPCLifeHistory()
    history.record(AutobiographicalMemory(
        "memory-1", "alice", "event-1", 2, ("bob",),
        "The event was frightening", 0.9, -0.2, turning_point=True,
    ))
    history.record(AutobiographicalMemory(
        "memory-2", "alice", "event-2", 5, ("bob",),
        "A later event was frightening", 0.8, -0.1, turning_point=True,
    ))
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("association-1", "memory-1", "smoke", "fear"),
        EmotionalMemoryAssociation("association-2", "memory-2", "fire", "fear"),
    ))
    response = EmotionalMemoryAdapter.evaluate(
        history, profile, {"smoke": 1.0, "fire": 1.0}, 5,
    )
    proposals = EmotionalScarFormationAdapter.propose(
        history, response, EmotionalScarFormationPolicy("policy"),
    )
    ledger = EmotionalScarDecisionLedger()
    for proposal in proposals:
        ledger.add_proposal(proposal)
    first, second = sorted(proposals, key=lambda p: p.proposed_tick)
    ledger.decide(EmotionalScarDecision("decision-1", first.proposal_id, "alice", 3, True, "accepted"))
    first_scar = ledger.scars.scars()[0]
    ledger.scars.recover(
        recovery_id="recovery-1", scar_id=first_scar.scar_id, owner_id="alice",
        tick=4, amount=0.1, method="support",
    )
    ledger.decide(EmotionalScarDecision("decision-2", second.proposal_id, "alice", 5, True, "accepted"))
    restored = EmotionalScarDecisionSnapshot.capture(ledger).restore()
    assert restored.snapshot() == ledger.snapshot()
    assert restored.scars.recoveries() == ledger.scars.recoveries()
    assert len(restored.scars.scars()) == 2
