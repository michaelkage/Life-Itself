import unittest

from simreality import (
    ActionTag, AgeBand, Description, NPC, NPCCollectionSnapshot, NPCMemory,
    NPCStateSnapshot, SocialInteraction, SocialTrustLedger, SocialTrustSnapshot, TraumaLevel,
)


class NPCStateSnapshotTests(unittest.TestCase):
    def make_npc(self):
        npc = NPC(
            entity_id="witness-1",
            age_band=AgeBand.SENIOR,
            moral_shackle=0.63,
            desperation_index=1.25,
            trauma_level=TraumaLevel.ANXIOUS,
            personal_stress=0.7,
        )
        npc.remember(NPCMemory(
            witness_id="witness-1",
            target_entity_id="actor-9",
            initial_impact=0.8,
            retention=0.61,
            timestamp_hour=17.5,
            action_tag=ActionTag.CRIME_THEFT,
            description=Description(
                height_m=1.81,
                height_uncertainty_m=0.2,
                jacket_colour_weights={"blue": 0.4, "black": 0.8},
                masked=True,
                masked_confidence=0.9,
                observations=2,
            ),
        ))
        return npc

    def test_npc_round_trip_preserves_identity_state_and_memories(self):
        npc = self.make_npc()
        snapshot = NPCStateSnapshot.capture(npc)
        payload = snapshot.to_json()
        restored = NPCStateSnapshot.from_json(payload).restore()
        self.assertEqual(restored, npc)
        self.assertEqual(NPCStateSnapshot.capture(restored).to_json(), payload)

    def test_collection_is_canonical_and_restores_by_id(self):
        first = self.make_npc()
        second = NPC(entity_id="citizen-2")
        snapshot = NPCCollectionSnapshot.capture([second, first])
        payload = snapshot.to_json()
        restored = NPCCollectionSnapshot.from_json(payload).restore()
        self.assertEqual(tuple(restored), ("citizen-2", "witness-1"))
        self.assertEqual(restored["witness-1"], first)
        self.assertEqual(NPCCollectionSnapshot.from_json(payload).to_json(), payload)

    def test_duplicate_npc_ids_rejected(self):
        with self.assertRaises(ValueError):
            NPCCollectionSnapshot.capture([NPC("same"), NPC("same")])

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            NPCStateSnapshot.from_json('{"schema_version":99}')

    def test_social_trust_round_trip_replays_same_relationship_state(self):
        ledger = SocialTrustLedger({("witness-1", "actor-9"): 0.2})
        ledger.add(SocialInteraction("i2", "witness-1", "actor-9", 1, 0.5, 4, "help"))
        ledger.add(SocialInteraction("i1", "witness-1", "actor-9", -1, 0.3, 2, "threat"))
        snapshot = SocialTrustSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = SocialTrustSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(SocialTrustSnapshot.capture(restored).to_json(), payload)

    def test_social_trust_snapshot_rejects_unknown_schema(self):
        with self.assertRaises(ValueError):
            SocialTrustSnapshot.from_json('{"schema_version":9}')

    def test_non_finite_json_rejected(self):
        with self.assertRaises(ValueError):
            NPCStateSnapshot.from_json('{"schema_version":1,"entity_id":"x","age_band":"Adult","moral_shackle":NaN,"desperation_index":0,"trauma_level":0,"personal_stress":0,"memories":[]}')

if __name__ == "__main__":
    unittest.main()
