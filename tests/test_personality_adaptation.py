import pytest

from simreality.identity_decisions import IdentityDecisionLedger
from simreality.identity_evolution import NPCIdentityProfile
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.personality_adaptation import (
    PersonalityAdaptationAdapter, PersonalityAdaptationRule,
)


def make_history():
    return NPCLifeHistory((
        AutobiographicalMemory(
            "m1", "alice", "event-1", 1, ("bob",),
            "I helped someone and they stood by me", 0.7, 0.4,
            tags=("support",),
        ),
        AutobiographicalMemory(
            "m2", "alice", "event-2", 2, ("cara",),
            "A neighbour supported me again", 0.6, 0.3,
            tags=("support",),
        ),
        AutobiographicalMemory(
            "m3", "alice", "event-3", 3, ("dan",),
            "A difficult day changed how I see people", 0.5, -0.1,
            tags=("support",),
        ),
    ))


def test_repeated_experiences_propose_small_cumulative_personality_change():
    history = make_history()
    profile = NPCIdentityProfile("alice", {"openness": 0.1})
    rule = PersonalityAdaptationRule(
        "support-openness", "support", "openness", 0.05,
        minimum_memories=3, maximum_delta=0.02,
    )
    result = PersonalityAdaptationAdapter.propose(
        history, (profile,), (rule,), current_tick=3,
        role_by_npc={"alice": "participant"},
    )
    assert len(result) == 1
    assessment = result[0]
    assert len(assessment.contributions) == 3
    assert assessment.proposal.delta == pytest.approx(0.02)
    assert assessment.proposal.before == pytest.approx(0.1)
    assert assessment.proposal.after == pytest.approx(0.12)
    assert assessment.proposal.evidence_strength == pytest.approx(0.8)


def test_personality_change_requires_explicit_acceptance_and_rejection_is_preserved():
    history = make_history()
    initial = NPCIdentityProfile("alice", {"openness": 0.1})
    rule = PersonalityAdaptationRule("support-openness", "support", "openness", 0.05)
    assessment = PersonalityAdaptationAdapter.propose(
        history, (initial,), (rule,), current_tick=3,
        role_by_npc={"alice": "witness"},
    )[0]
    decisions = IdentityDecisionLedger((initial,))
    decisions.decide(
        "decision-reject", assessment.proposal, accepted=False,
        decision_tick=4, rationale="I do not see myself that way",
    )
    assert decisions.traits_for("alice")["openness"] == pytest.approx(0.1)
    assert decisions.entries()[0].accepted is False

    # A separate NPC/axis ledger demonstrates acceptance applies the same
    # proposal only after the NPC explicitly accepts it.
    accepted = IdentityDecisionLedger((initial,))
    accepted.decide(
        "decision-accept", assessment.proposal, accepted=True,
        decision_tick=4, rationale="These experiences changed me",
    )
    assert accepted.traits_for("alice")["openness"] == pytest.approx(0.12)


def test_opposing_experiences_can_cancel_and_old_memories_lose_weight():
    history = NPCLifeHistory((
        AutobiographicalMemory("old-positive", "alice", "e1", 0, (), "Old positive", 0.5, 0.8, tags=("change",)),
        AutobiographicalMemory("recent-negative", "alice", "e2", 100, (), "Recent negative", 0.5, -0.8, tags=("change",)),
    ))
    profile = NPCIdentityProfile("alice", {"trust": 0.0})
    rule = PersonalityAdaptationRule(
        "change-trust", "change", "trust", 0.05,
        minimum_memories=2, half_life_ticks=100.0, maximum_delta=0.05,
    )
    result = PersonalityAdaptationAdapter.propose(
        history, (profile,), (rule,), current_tick=100,
        role_by_npc={"alice": "participant"},
    )
    assert len(result) == 1
    assert result[0].proposal.delta == pytest.approx(-0.02)


def test_future_memories_missing_roles_and_invalid_rules_are_rejected():
    history = NPCLifeHistory((
        AutobiographicalMemory("future-1", "alice", "e1", 9, (), "Future one", 0.5, 0.2, tags=("x",)),
        AutobiographicalMemory("future-2", "alice", "e2", 10, (), "Future two", 0.5, 0.2, tags=("x",)),
    ))
    profile = NPCIdentityProfile("alice", {"confidence": 0.0})
    rule = PersonalityAdaptationRule("x-confidence", "x", "confidence", 0.05)
    with pytest.raises(ValueError, match="future memory"):
        PersonalityAdaptationAdapter.propose(
            history, (profile,), (rule,), current_tick=8,
            role_by_npc={"alice": "participant"},
        )
    with pytest.raises(ValueError, match="missing participant/witness role"):
        PersonalityAdaptationAdapter.propose(
            make_history(), (profile,), (rule,), current_tick=10, role_by_npc={},
        )
    with pytest.raises(ValueError):
        PersonalityAdaptationRule("bad", "x", "confidence", 0.05, maximum_delta=0.2)


def test_thresholds_prevent_one_experience_from_rewriting_personality():
    history = make_history()
    profile = NPCIdentityProfile("alice", {"resilience": 0.0})
    rule = PersonalityAdaptationRule(
        "support-resilience", "support", "resilience", 0.05,
        minimum_memories=4,
    )
    assert PersonalityAdaptationAdapter.propose(
        history, (profile,), (rule,), current_tick=3,
        role_by_npc={"alice": "participant"},
    ) == ()
