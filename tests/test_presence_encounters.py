import unittest

from simreality import ActionTag, Description, NPC, NPCMemory
from simreality.presence import PresenceLedger
from simreality.presence_encounters import PresenceEncounterLedger, PresenceSocialAdapter
from simreality.presence_encounter_save_state import PresenceEncounterSnapshot
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger
from simreality.world_events import WorldEventLedger


class PresenceSocialTests(unittest.TestCase):
    def setup_world(self):
        presence = PresenceLedger()
        presence.place("a", "cafe", 1)
        presence.place("b", "cafe", 1)
        presence.place("c", "home", 1)
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        conversations = SocialConversationAdapter(trust, beliefs)
        return presence, trust, conversations, PresenceSocialAdapter(presence)

    def npc(self, name, target):
        npc = NPC(name)
        npc.remember(NPCMemory(name, target, 0.8, 0.8, 0.0, ActionTag.CRIME_THEFT,
                               Description(height_m=1.8, height_uncertainty_m=0.2)))
        return npc

    def test_colocation_alone_does_not_create_encounter(self):
        presence, _, _, adapter = self.setup_world()
        self.assertIsNone(adapter.encounter("e0", "a", "b", 2, opportunity=False))
        self.assertEqual(adapter.ledger.snapshot(), ())

    def test_encounter_requires_both_present_at_same_location(self):
        _, _, _, adapter = self.setup_world()
        with self.assertRaisesRegex(ValueError, "share a physical location"):
            adapter.encounter("e1", "a", "c", 2, opportunity=True)

    def test_encounter_records_event_and_is_replay_safe(self):
        presence, _, _, adapter = self.setup_world()
        events = WorldEventLedger()
        first = adapter.encounter("e2", "a", "b", 2, opportunity=True, events=events)
        second = adapter.encounter("e2", "a", "b", 2, opportunity=True, events=events)
        self.assertEqual(first, second)
        self.assertEqual(events.query(event_type="npc_encounter")[0].participants, ("a", "b"))
        with self.assertRaisesRegex(ValueError, "conflicting"):
            adapter.encounter("e2", "a", "b", 2, opportunity=True, location_id="different")

    def test_conversation_requires_explicit_request_and_transfers_memory(self):
        presence, trust, conversations, adapter = self.setup_world()
        listener, speaker = self.npc("a", "old"), self.npc("b", "target")
        result = adapter.encounter("e3", "a", "b", 2, opportunity=True, conversation=True,
                                   conversation_id="chat-e3", listener=listener, speaker=speaker,
                                   conversation_adapter=conversations)
        self.assertIsNotNone(result.conversation)
        self.assertEqual(len(listener.memories), 1)

    def test_trust_changes_only_with_explicit_direction_policy(self):
        _, trust, _, adapter = self.setup_world()
        adapter.encounter("e4", "a", "b", 2, opportunity=True, trust=trust,
                          trust_directions=(1, -1), trust_strength=0.5)
        self.assertGreater(trust.get("a", "b").trust, 0.5)
        self.assertLess(trust.get("b", "a").trust, 0.5)

    def test_encounter_snapshot_preserves_replay(self):
        _, _, _, adapter = self.setup_world()
        adapter.encounter("e5", "a", "b", 2, opportunity=True)
        payload = PresenceEncounterSnapshot.capture(adapter.ledger).to_json()
        restored = PresenceEncounterSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), adapter.ledger.snapshot())
        self.assertEqual(restored.tick_snapshot(), adapter.ledger.tick_snapshot())


if __name__ == "__main__":
    unittest.main()
