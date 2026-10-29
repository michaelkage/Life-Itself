"""Persistence tests for institutional routine records."""
import unittest

from simreality.routine_institution_ledger import RoutineInstitutionLedger
from simreality.routine_institution_save_state import RoutineInstitutionSnapshot
from simreality.world_events import WorldEventLedger


class RoutineInstitutionSnapshotTests(unittest.TestCase):
    def test_round_trip_preserves_records_and_replay_protection(self):
        event = WorldEventLedger.make_event(
            "late-1", 3, "workplace_late_arrival", participants=("npc-1",),
            attributes={"location_id": "bakery", "delay_minutes": 12},
        )
        ledger = RoutineInstitutionLedger()
        ledger.apply((event,))
        restored = RoutineInstitutionSnapshot.from_json(
            RoutineInstitutionSnapshot.capture(ledger).to_json()
        ).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(restored.apply((event,)), ())
        self.assertEqual(restored.get("bakery", "npc-1").total_delay_minutes, 12)

    def test_unknown_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, "schema"):
            RoutineInstitutionSnapshot.from_json('{"schema_version":2}')


if __name__ == "__main__":
    unittest.main()
