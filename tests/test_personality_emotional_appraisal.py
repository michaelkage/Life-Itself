import pytest
from simreality.emotional_memory import EmotionalMemoryAdapter, EmotionalMemoryAssociation, EmotionalMemoryProfile
from simreality.identity_evolution import NPCIdentityProfile
from simreality.npc_life_history import AutobiographicalMemory, NPCLifeHistory
from simreality.personality_emotional_appraisal import PersonalityEmotionAdapter, PersonalityEmotionRule

def setup_response():
    history = NPCLifeHistory((AutobiographicalMemory("memory-1", "alice", "event-1", 2, (), "A frightening event", 0.8, 0.9, tags=("fear",)),))
    profile = EmotionalMemoryProfile("alice", (EmotionalMemoryAssociation("association-1", "memory-1", "loud-noise", "fear"),))
    return EmotionalMemoryAdapter.evaluate(history, profile, {"loud-noise": 1.0}, 2)

def test_personality_changes_reaction_to_same_memory_cue():
    response = setup_response()
    rule = PersonalityEmotionRule("sensitivity", "fear", "threat_sensitivity", 0.5)
    high = PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("alice", {"threat_sensitivity": 1.0}), (rule,))
    low = PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("alice", {"threat_sensitivity": -1.0}), (rule,))
    assert dict(high.intensities)["fear"] == pytest.approx(1.0)
    assert dict(low.intensities)["fear"] == pytest.approx(0.45)
    assert high.contributions[0].trait_axis == "threat_sensitivity"

def test_unruled_emotions_pass_through_deterministically():
    response = setup_response()
    identity = NPCIdentityProfile("alice", {"openness": 0.7})
    assert PersonalityEmotionAdapter.evaluate(response, identity, ()) == PersonalityEmotionAdapter.evaluate(response, identity, ())
    result = PersonalityEmotionAdapter.evaluate(response, identity, ())
    assert dict(result.intensities)["fear"] == pytest.approx(0.9)
    assert result.contributions[0].rule_id is None

def test_owner_missing_trait_and_duplicate_rules_are_rejected():
    response = setup_response()
    with pytest.raises(ValueError, match="owner"):
        PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("bob", {"trait": 0.2}), ())
    rule = PersonalityEmotionRule("r", "fear", "missing", 0.5)
    with pytest.raises(KeyError, match="no trait axis"):
        PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("alice", {}), (rule,))
    duplicate = PersonalityEmotionRule("r2", "fear", "other", 0.2)
    with pytest.raises(ValueError, match="one personality rule"):
        PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("alice", {"missing": 0.1, "other": 0.2}), (rule, duplicate))

def test_gain_is_bounded_and_source_is_not_mutated():
    response = setup_response()
    result = PersonalityEmotionAdapter.evaluate(response, NPCIdentityProfile("alice", {"trait": 1.0}), (PersonalityEmotionRule("r", "fear", "trait", 1.0),))
    assert dict(result.intensities)["fear"] == 1.0
    assert response == setup_response()
    with pytest.raises(ValueError, match="coefficient"):
        PersonalityEmotionRule("bad", "fear", "trait", 1.1)