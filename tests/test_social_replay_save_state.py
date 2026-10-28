import unittest

from simreality import (
    ActionTag, Description, NPC, NPCMemory, ObservedClaim,
    SocialBeliefSystem, SocialConsequenceRecorder, SocialConversationAdapter,
    SocialConversationReplaySnapshot, SocialConsequenceReplaySnapshot,
    SocialTrustLedger, WitnessedSocialEvent,
)


class SocialReplayPersistenceTests(unittest.TestCase):
    def make_npc(self, entity_id, with_memory=False):
        npc = NPC(entity_id)
        if with_memory:
            npc.remember(NPCMemory(
                entity_id, "target", 0.8, 0.8, 2.0, ActionTag.CRIME_THEFT,
                Description(1.8, 0.2, {"black": 0.8}, False, 0.2, 1),
            ))
        return npc

    def test_conversation_replay_round_trip_returns_saved_result(self):
        trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        beliefs = SocialBeliefSystem(trust)
        adapter = SocialConversationAdapter(trust, beliefs)
        listener = self.make_npc("listener")
        speaker = self.make_npc("speaker", True)
        first = adapter.converse("chat-1", listener, speaker, 3, "D1")
        payload = SocialConversationReplaySnapshot.capture(adapter).to_json()

        restored_trust = SocialTrustLedger({("listener", "speaker"): 0.9})
        restored_beliefs = SocialBeliefSystem(restored_trust)
        # In a complete save, belief state is restored before the adapter replay index.
        from simreality import BeliefLedgerSnapshot, SocialBeliefSnapshot
        restored_beliefs = SocialBeliefSnapshot.from_json(SocialBeliefSnapshot.capture(beliefs).to_json()).restore(restored_trust)
        restored = SocialConversationAdapter(restored_trust, restored_beliefs)
        SocialConversationReplaySnapshot.from_json(payload).restore(restored)
        restored_listener = self.make_npc("listener")
        restored_speaker = self.make_npc("speaker", True)
        replay = restored.converse("chat-1", restored_listener, restored_speaker, 3, "D1")
        self.assertEqual(replay, first)
        self.assertEqual(restored_listener.memories, [])
        self.assertEqual(SocialConversationReplaySnapshot.capture(restored).to_json(), payload)

    def test_consequence_replay_round_trip_does_not_repeat_side_effects(self):
        trust = SocialTrustLedger({("witness", "actor"): 0.5})
        beliefs = SocialBeliefSystem(trust)
        recorder = SocialConsequenceRecorder(trust, beliefs)
        event = WitnessedSocialEvent(
            "event-1", "witness", "actor", 5, -1, 0.6,
            (ObservedClaim("claim-1", 1, 0.7),),
        )
        first = recorder.record(event)
        payload = SocialConsequenceReplaySnapshot.capture(recorder).to_json()

        from simreality import BeliefLedgerSnapshot, SocialBeliefSnapshot, SocialTrustSnapshot
        trust_payload = SocialTrustSnapshot.capture(trust).to_json()
        beliefs_payload = SocialBeliefSnapshot.capture(beliefs).to_json()
        restored_trust = SocialTrustSnapshot.from_json(trust_payload).restore()
        restored_beliefs = SocialBeliefSnapshot.from_json(beliefs_payload).restore(restored_trust)
        restored = SocialConsequenceRecorder(restored_trust, restored_beliefs)
        SocialConsequenceReplaySnapshot.from_json(payload).restore(restored)
        before_trust = restored_trust.snapshot()
        replay = restored.record(event)
        self.assertEqual(replay, first)
        self.assertEqual(restored_trust.snapshot(), before_trust)
        self.assertEqual(SocialConsequenceReplaySnapshot.capture(restored).to_json(), payload)

    def test_unknown_schemas_rejected(self):
        with self.assertRaises(ValueError):
            SocialConversationReplaySnapshot.from_json('{"schema_version":77,"entries":[]}')
        with self.assertRaises(ValueError):
            SocialConsequenceReplaySnapshot.from_json('{"schema_version":77,"entries":[]}')


if __name__ == "__main__":
    unittest.main()
