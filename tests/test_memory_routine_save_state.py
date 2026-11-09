import unittest

from simreality.memory_location_book import MemoryLocationAssociationBook
from simreality.memory_routine_save_state import MemoryLocationAssociationSnapshot
from simreality.memory_routines import MemoryLocationAssociation


class MemoryLocationAssociationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.book = MemoryLocationAssociationBook((
            ("npc-2", MemoryLocationAssociation("home-memory", 1, "old-home", 0.7)),
            ("npc-1", MemoryLocationAssociation("incident", 0, "station", 0.9, "side-street")),
        ))

    def test_canonical_round_trip_preserves_owner_scoped_links(self):
        snapshot = MemoryLocationAssociationSnapshot.capture(self.book)
        payload = snapshot.to_json()
        restored = MemoryLocationAssociationSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), self.book.snapshot())
        self.assertEqual(restored.for_owner("npc-1")[0].location_id, "station")
        self.assertEqual(payload, MemoryLocationAssociationSnapshot.capture(restored).to_json())

    def test_same_association_id_is_allowed_for_different_npcs(self):
        book = MemoryLocationAssociationBook()
        book.add("npc-1", MemoryLocationAssociation("same", 0, "street"))
        book.add("npc-2", MemoryLocationAssociation("same", 0, "street"))
        self.assertEqual(len(book.snapshot()), 2)

    def test_duplicate_owner_association_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.book.add("npc-1", MemoryLocationAssociation("incident", 2, "other"))

    def test_remove_is_owner_scoped_and_idempotent(self):
        self.assertTrue(self.book.remove("npc-1", "incident"))
        self.assertFalse(self.book.remove("npc-1", "incident"))
        self.assertEqual(len(self.book.for_owner("npc-2")), 1)

    def test_invalid_schema_and_noncanonical_entries_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            MemoryLocationAssociationSnapshot.from_json('{"schema_version":99,"entries":[]}')
        reversed_entries = tuple(reversed(self.book.snapshot()))
        with self.assertRaisesRegex(ValueError, "sorted"):
            MemoryLocationAssociationSnapshot(reversed_entries)


if __name__ == "__main__":
    unittest.main()
