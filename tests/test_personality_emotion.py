import pytest
from simreality.emotional_memory import EmotionalMemoryAdapter, EmotionalMemoryAssociation, EmotionalMemoryProfile
from simreality.identity_evolution import NPCIdentityProfile
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.personality_emotion import PersonalityEmotionAdapter, PersonalityEmotionRule

def inputs():
    history = NPCLifeHistory((AutobiographicalMemory(
        "m1", "alice", "e1", 1, (), "A frightening incident", 0.8, 0.9,
    ),))
    profile = EmotionalMemoryProfile("alice", (
        EmotionalMemoryAssociation("a1", "m1", "sirens", "fear"),
    ))
    return EmotionalMemoryAdapter.evaluate(history, profile, {"sirens": 1.0}, 1)

def test_personality_changes_same_memory_response_by_explicit_rule():
    response = inputs()
    rule = PersonalityEmotionRule("anxiety", "fear", 0.5)
    anxious = NPCIdentityProfile("alice", {"anxiety": 1.0})
    resilient = NPCIdentityProfile("alice", {"anxiety": -0.5})
    high = PersonalityEmotionAdapter.assess(response, anxious, (rule,))
    low = PersonalityEmotionAdapter.assess(response, resilient, (rule,))
    base = dict(response.intensities)["fear"]
    assert dict(high.intensities)["fear"] == pytest.approx(base * 1.5)
    assert dict(low.intensities)["fear"] == pytest.approx(base * 0.75)
    assert high.contributions[0].memory_id == "m1"

def test_modifier_is_bounded_and_can_suppress_to_zero():
    response = inputs()
    profile = NPCIdentityProfile("alice", {"avoidance": 1.0}, {"avoidance": 2.0})
    result = PersonalityEmotionAdapter.assess(
        response, profile, (PersonalityEmotionRule("avoidance", "fear", -1.0),))
    assert dict(result.intensities)["fear"] == 0.0
    assert all(0.0 <= value <= 1.0 for _, value in result.intensities)

def test_unmapped_traits_leave_response_unchanged():
    response = inputs()
    result = PersonalityEmotionAdapter.assess(
        response, NPCIdentityProfile("alice", {"optimism": 0.8}), ())
    assert result.intensities == response.intensities
    assert result.contributions == ()

def test_owner_mismatch_and_duplicate_rules_are_rejected():
    response = inputs()
    with pytest.raises(ValueError, match="owner"):
        PersonalityEmotionAdapter.assess(response, NPCIdentityProfile("bob", {}), ())
    profile = NPCIdentityProfile("alice", {"anxiety": 1.0})
    rule = PersonalityEmotionRule("anxiety", "fear", 0.5)
    with pytest.raises(ValueError, match="duplicate"):
        PersonalityEmotionAdapter.assess(response, profile, (rule, rule))

def test_source_response_is_not_mutated():
    response = inputs()
    result = PersonalityEmotionAdapter.assess(
        response, NPCIdentityProfile("alice", {"anxiety": 1.0}),
        (PersonalityEmotionRule("anxiety", "fear", 0.5),))
    assert result.source_response is response
    assert response.intensities == result.source_response.intensities
