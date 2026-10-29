import unittest

from simreality.memory_routines import MemoryLocationAssociation, MemoryRoutineAdapter
from simreality.model import ActionTag, AgeBand, Description, NPC, NPCMemory
from simreality.routines import DisruptionKind


def memory(witness, target, retention, tag=ActionTag.CRIME_ASSAULT):
    return NPCMemory(witness, target, retention, retention, 1.0, tag, Description())


class MemoryRoutineAdapterTests(unittest.TestCase):
    def setUp(self):
        self.npc = NPC("witness-1", age_band=AgeBand.ADULT, memories=[
            memory("witness-1", "person-1", 0.9),
            memory("witness-1", "person-2", 0.2, ActionTag.INTERACTION_POLITE),
        ])
        self.adapter = MemoryRoutineAdapter()

    def test_only_explicitly_linked_retained_memory_causes_avoidance(self):
        result = self.adapter.derive_avoidance(
            self.npc,
            (MemoryLocationAssociation("assoc-a", 0, "alley", 1.0, "main-road"),
             MemoryLocationAssociation("assoc-b", 1, "cafe", 1.0)),
            start_minute=480, end_minute=600, minimum_strength=0.25,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].owner_id, "witness-1")
        self.assertEqual(result[0].kind, DisruptionKind.LOCATION_AVOIDANCE)
        self.assertEqual(result[0].affected_location_id, "alley")
        self.assertEqual(result[0].alternative_location_id, "main-road")
        self.assertGreater(result[0].severity, 0.89)

    def test_same_inputs_are_deterministic_and_association_order_independent(self):
        associations = (
            MemoryLocationAssociation("assoc-a", 0, "alley", 0.5),
            MemoryLocationAssociation("assoc-b", 0, "alley", 0.5),
        )
        first = self.adapter.derive_avoidance(self.npc, associations, start_minute=480, end_minute=600)
        second = self.adapter.derive_avoidance(self.npc, tuple(reversed(associations)), start_minute=480, end_minute=600)
        self.assertEqual(first, second)
        self.assertEqual(first[0].severity, 0.6975)

    def test_different_npcs_get_personal_results(self):
        associations = (MemoryLocationAssociation("assoc-a", 0, "alley"),)
        fearful = self.adapter.derive_avoidance(self.npc, associations, start_minute=480, end_minute=600)
        other = NPC("witness-2", memories=[memory("witness-2", "person-1", 0.1)])
        less_affected = self.adapter.derive_avoidance(other, associations, start_minute=480, end_minute=600)
        self.assertEqual(len(fearful), 1)
        self.assertEqual(less_affected, ())

    def test_invalid_memory_links_and_duplicate_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "memory index out of range"):
            self.adapter.derive_avoidance(
                self.npc, (MemoryLocationAssociation("bad", 99, "alley"),),
                start_minute=480, end_minute=600,
            )
        with self.assertRaisesRegex(ValueError, "unique"):
            self.adapter.derive_avoidance(
                self.npc, (MemoryLocationAssociation("same", 0, "alley"),
                           MemoryLocationAssociation("same", 1, "cafe")),
                start_minute=480, end_minute=600,
            )


if __name__ == "__main__":
    unittest.main()
