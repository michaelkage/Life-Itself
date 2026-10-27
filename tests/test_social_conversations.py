"""Tests for replay-safe conversations feeding observer-specific beliefs."""
import unittest

from simreality import ActionTag, Description, NPC, NPCMemory
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger


class SocialConversationAdapterTests(unittest.TestCase):
    def make_npc(self, entity_id, memory=None):
        npc = NPC(entity_id)
        if memory is not None:
            npc.remember(NPCMemory(
                witness_id=entity_id,
                target_entity_id=memory[0],
                initial_impact=memory[1],
                retention=memory[1],
                timestamp_hour=0.0,
                action_tag=ActionTag.CRIME_THEFT,
                description=Description(
                    height_m=1.8,
                    height_uncertainty_m=0.25,
                    jacket_colour_weights={"black": 0.8},
                ),
            ))
        return npc

    def setup_adapter(self, trust_values=None):
        trust = SocialTrustLedger(trust_values or {})
        beliefs = SocialBeliefSystem(trust)
        return trust, beliefs, SocialConversationAdapter(trust, beliefs)

    def test_actual_conversation_transfers_memory_and_updates_belief(self):
        trust, beliefs, adapter = self.setup_adapter({("listener", "speaker"): 0.9})
        listener = self.make_npc("listener")
        speaker = self.make_npc("speaker", ("suspect", 0.8))
        result = adapter.converse("chat-1", listener, speaker, 10, "D1")
        self.assertEqual(result.conversation.npc_a, "speaker")
        self.assertEqual(result.conversation.npc_b, "listener")
        self.assertEqual(len(result.conversation.transferred), 1)
        self.assertEqual(len(listener.memories), 1)
        claim_id, confidence = result.belief_states[0]
        self.assertIn("suspect", claim_id)
        self.assertGreater(confidence, 0.5)
        self.assertEqual(beliefs.get("listener", claim_id).confidence, confidence)

    def test_unattributed_rumour_does_not_name_target_in_claim(self):
        _, beliefs, adapter = self.setup_adapter({("listener", "speaker"): 1.0})
        listener = self.make_npc("listener")
        speaker = self.make_npc("speaker", ("suspect", 0.4))
        result = adapter.converse("chat-2", listener, speaker, 11)
        claim_id, _ = result.belief_states[0]
        self.assertIn("unattributed", claim_id)
        self.assertNotIn("suspect", claim_id)
        self.assertIsNone(listener.memories[0].target_entity_id)

    def test_replay_does_not_duplicate_memory_or_belief(self):
        _, beliefs, adapter = self.setup_adapter({("listener", "speaker"): 0.8})
        listener = self.make_npc("listener")
        speaker = self.make_npc("speaker", ("suspect", 0.8))
        first = adapter.converse("chat-3", listener, speaker, 12)
        second = adapter.converse("chat-3", listener, speaker, 12)
        self.assertIs(first, second)
        self.assertEqual(len(listener.memories), 1)
        self.assertEqual(len(beliefs.beliefs_for("listener")), 1)
        self.assertEqual(adapter.snapshot(), (first,))

    def test_reusing_id_with_changed_input_is_rejected(self):
        _, _, adapter = self.setup_adapter()
        listener = self.make_npc("listener")
        speaker = self.make_npc("speaker", ("suspect", 0.8))
        adapter.converse("chat-4", listener, speaker, 12)
        changed_speaker = self.make_npc("speaker", ("other-suspect", 0.8))
        with self.assertRaises(ValueError):
            adapter.converse("chat-4", listener, changed_speaker, 12)

    def test_requires_shared_trust_ledger(self):
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(SocialTrustLedger())
        with self.assertRaises(ValueError):
            SocialConversationAdapter(trust, beliefs)


if __name__ == "__main__":
    unittest.main()
