import unittest

from simreality.emotional_events import (
    EmotionalDecayRule, EmotionalEventRule, EmotionalRelationshipRule,
    EmotionalMemoryRule, NPCEmotionalEventLedger,
)
from simreality.world_events import WorldEventLedger
from simreality.social_trust import SocialInteraction, SocialTrustLedger
from simreality.identity_context import NPCEmotionalState
from simreality.model import ActionTag, Description, NPC, NPCMemory


class NPCEmotionalEventLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = NPCEmotionalEventLedger()
        self.grief = EmotionalEventRule("bereaved-grief", "bereavement", "participant", "grief", 0.7)
        self.witness_fear = EmotionalEventRule("witness-fear", "bereavement", "witness", "fear", 0.3)
        self.decay = (EmotionalDecayRule("grief", 0.9), EmotionalDecayRule("fear", 0.8))

    def event(self, event_id="loss-1", tick=2, event_type="bereavement"):
        return WorldEventLedger.make_event(
            event_id, tick, event_type,
            participants=("npc-a",), witnesses=("npc-b",),
            attributes={"context": "close_relationship"},
        )

    def test_events_change_only_explicit_participants_and_witnesses(self):
        states = self.ledger.advance(2, (self.event(),),
                                     event_rules=(self.grief, self.witness_fear))
        by_id = {state.npc_id: dict(state.intensities) for state in states}
        self.assertEqual(by_id["npc-a"], {"grief": 0.7})
        self.assertEqual(by_id["npc-b"], {"fear": 0.3})

    def test_event_impulse_occurs_at_event_tick_then_decays_to_current_tick(self):
        state = self.ledger.advance(4, (self.event(),),
                                   event_rules=(self.grief,), decay_rules=self.decay)[0]
        self.assertEqual(state.npc_id, "npc-a")
        self.assertAlmostEqual(state.intensities["grief"], 0.7 * 0.9**2)
        self.assertEqual(state.sampled_tick, 4)

    def test_retries_and_snapshot_restore_are_idempotent(self):
        event = self.event()
        self.ledger.advance(2, (event,), event_rules=(self.grief,))
        restored = NPCEmotionalEventLedger.from_snapshot(self.ledger.snapshot())
        repeated = restored.advance(5, (event,), event_rules=(self.grief,),
                                    decay_rules=self.decay)
        self.assertAlmostEqual(repeated[0].intensities["grief"], 0.7 * 0.9**3)
        restored.advance(5, (event,), event_rules=(self.grief,), decay_rules=self.decay)
        self.assertAlmostEqual(restored.state_for("npc-a").intensities["grief"],
                               0.7 * 0.9**3)

    def test_conflicting_event_reuse_and_late_new_events_are_rejected(self):
        event = self.event()
        self.ledger.advance(3, (event,), event_rules=(self.grief,))
        conflict = self.event(event_id="loss-1", tick=2, event_type="betrayal")
        with self.assertRaisesRegex(ValueError, "conflicting content"):
            self.ledger.advance(3, (conflict,), event_rules=(self.grief,))
        with self.assertRaisesRegex(ValueError, "before current_tick"):
            self.ledger.advance(4, (self.event("late-arrival", tick=1),),
                                event_rules=(self.grief,))

    def test_relationship_is_sampled_at_event_tick_not_processing_tick(self):
        trust = SocialTrustLedger({
            ("npc-a", "npc-target"): 0.9,
            ("npc-b", "npc-target"): 0.1,
        })
        # These later interactions reverse the live relationship direction.
        trust.add(SocialInteraction("later-a", "npc-a", "npc-target", -1, 1.0, 7))
        trust.add(SocialInteraction("later-b", "npc-b", "npc-target", 1, 1.0, 7))
        event = WorldEventLedger.make_event(
            "betrayal-1", 5, "betrayal",
            participants=("npc-a", "npc-b"),
            attributes={"target_id": "npc-target"},
        )
        initial = {
            npc_id: NPCEmotionalState(npc_id, 5, {"anger": 0.5})
            for npc_id in ("npc-a", "npc-b")
        }
        ledger = NPCEmotionalEventLedger(initial, current_tick=5)
        rule = EmotionalRelationshipRule(
            "trusted-target-anger", "betrayal", "participant",
            "anger", "target_id", 0.5,
        )
        states = ledger.advance(
            5, (event,), event_rules=(), relationship_rules=(rule,),
            trust_ledger=trust,
        )
        by_id = {state.npc_id: state.intensities["anger"] for state in states}
        self.assertAlmostEqual(by_id["npc-a"], 0.9)
        self.assertAlmostEqual(by_id["npc-b"], 0.1)
        # Replaying after more relationship history cannot rewrite the event reaction.
        trust.add(SocialInteraction("much-later-a", "npc-a", "npc-target", 1, 1.0, 9))
        ledger.advance(6, (event,), event_rules=(), relationship_rules=(rule,),
                       trust_ledger=trust)
        self.assertAlmostEqual(ledger.state_for("npc-a").intensities["anger"], 0.9)

    def test_relationship_rule_missing_target_is_neutral_and_requires_trust(self):
        event = WorldEventLedger.make_event(
            "ambiguous", 1, "betrayal", participants=("npc-a",),
        )
        rule = EmotionalRelationshipRule(
            "relationship-anger", "betrayal", "participant",
            "anger", "target_id", 0.5,
        )
        with self.assertRaisesRegex(TypeError, "SocialTrustLedger"):
            self.ledger.advance(1, (event,), event_rules=(),
                                relationship_rules=(rule,))
        states = self.ledger.advance(
            1, (event,), event_rules=(), relationship_rules=(rule,),
            trust_ledger=SocialTrustLedger(),
        )
        self.assertEqual(self.ledger.state_for("npc-a").intensities, {})

    def test_personal_memories_condition_the_same_event_differently(self):
        event = WorldEventLedger.make_event(
            "betrayal-now", 4, "betrayal", participants=("npc-a", "npc-b"),
            attributes={"target_entity_id": "person-x", "action_tag": ActionTag.CRIME_ASSAULT.value},
        )
        def memory(owner, target, tag, retention):
            return NPCMemory(owner, target, retention, retention, 1.0, tag, Description())
        npcs = {
            "npc-a": NPC("npc-a", memories=[memory("npc-a", "person-x", ActionTag.CRIME_ASSAULT, 0.8),
                                                    memory("npc-a", "other", ActionTag.CRIME_ASSAULT, 1.0)]),
            "npc-b": NPC("npc-b", memories=[memory("npc-b", "person-x", ActionTag.CRIME_ASSAULT, 0.1),
                                                    memory("npc-b", "person-x", ActionTag.INTERACTION_POLITE, 1.0)]),
        }
        rule = EmotionalMemoryRule(
            "past-assault-anger", "betrayal", "participant", "anger", coefficient=0.5,
            minimum_retention=0.05,
        )
        states = self.ledger.advance(4, (event,), event_rules=(),
                                     memory_rules=(rule,), npcs_by_id=npcs)
        by_id = {state.npc_id: state.intensities["anger"] for state in states}
        self.assertAlmostEqual(by_id["npc-a"], 0.4)
        self.assertAlmostEqual(by_id["npc-b"], 0.05)

    def test_memory_effect_is_not_recomputed_when_memory_later_decays(self):
        event = WorldEventLedger.make_event(
            "betrayal-memory", 4, "betrayal", participants=("npc-a",),
            attributes={"target_entity_id": "person-x", "action_tag": ActionTag.CRIME_ASSAULT.value},
        )
        memory = NPCMemory("npc-a", "person-x", 0.8, 0.8, 1.0, ActionTag.CRIME_ASSAULT, Description())
        npc = NPC("npc-a", memories=[memory])
        rule = EmotionalMemoryRule("memory-grief", "betrayal", "participant", "grief", coefficient=0.5)
        self.ledger.advance(4, (event,), event_rules=(), memory_rules=(rule,), npcs_by_id={"npc-a": npc})
        npc.memories[0] = npc.memories[0].decayed_to(0.1)
        self.ledger.advance(5, (event,), event_rules=(), memory_rules=(rule,), npcs_by_id={"npc-a": npc})
        self.assertAlmostEqual(self.ledger.state_for("npc-a").intensities["grief"], 0.4)

    def test_memory_rules_require_npc_context_and_valid_event_tag(self):
        rule = EmotionalMemoryRule("memory-rule", "betrayal", "participant", "grief")
        event = WorldEventLedger.make_event(
            "bad-tag", 1, "betrayal", participants=("npc-a",),
            attributes={"target_entity_id": "person-x", "action_tag": "not-a-tag"},
        )
        with self.assertRaisesRegex(TypeError, "NPC mapping"):
            self.ledger.advance(1, (event,), event_rules=(), memory_rules=(rule,))
        with self.assertRaisesRegex(ValueError, "unknown"):
            self.ledger.advance(1, (event,), event_rules=(), memory_rules=(rule,),
                                npcs_by_id={"npc-a": NPC("npc-a")})

    def test_decay_without_events_and_validation(self):
        self.ledger.advance(2, (self.event(),), event_rules=(self.grief,))
        state = self.ledger.advance(4, (), event_rules=(),
                                    decay_rules=(EmotionalDecayRule("grief", 0.5),))[0]
        self.assertAlmostEqual(state.intensities["grief"], 0.7 * 0.5**2)
        with self.assertRaises(ValueError):
            EmotionalEventRule("bad", "death", "observer", "grief", 0.2)
        with self.assertRaises(ValueError):
            EmotionalDecayRule("fear", 1.2)


if __name__ == "__main__":
    unittest.main()
