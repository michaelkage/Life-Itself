import pytest

from simreality.emotional_scars import EmotionalScar, NPCEmotionalScarLedger
from simreality.emotional_scars_save_state import EmotionalScarSnapshot


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
