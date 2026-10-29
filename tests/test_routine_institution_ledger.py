"""Tests for persistent institutional records from explicit consequence events."""
import unittest

from simreality.routine_institution_ledger import RoutineInstitutionLedger
from simreality.world_events import WorldEventLedger


class RoutineInstitutionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.late = self.events.append(WorldEventLedger.make_event(
            "late-1", 3, "workplace_late_arrival", participants=("npc-1",),
            attributes={"location_id": "bakery", "delay_minutes": 12},
        ))
        self.missed = self.events.append(WorldEventLedger.make_event(
            "missed-1", 4, "appointment_missed", participants=("npc-1",),
            attributes={"location_id": "clinic", "delay_minutes": 0},
        ))

    def test_records_accumulate_per_institution_and_person(self):
        ledger = RoutineInstitutionLedger()
        changed = ledger.apply((self.late, self.missed))
        self.assertEqual(len(changed), 2)
        bakery = ledger.get("bakery", "npc-1")
        self.assertEqual(bakery.late_arrivals, 1)
        self.assertEqual(bakery.total_delay_minutes, 12)
        clinic = ledger.get("clinic", "npc-1")
        self.assertEqual(clinic.missed_appointments, 1)

    def test_replay_is_idempotent(self):
        ledger = RoutineInstitutionLedger()
        ledger.apply((self.late,))
        first = ledger.snapshot()
        self.assertEqual(ledger.apply((self.late,)), ())
        self.assertEqual(ledger.snapshot(), first)

    def test_conflicting_event_id_rejected(self):
        ledger = RoutineInstitutionLedger()
        ledger.apply((self.late,))
        conflicting = WorldEventLedger.make_event(
            "late-1", 3, "workplace_late_arrival", participants=("npc-1",),
            attributes={"location_id": "bakery", "delay_minutes": 99},
        )
        with self.assertRaisesRegex(ValueError, "different content"):
            ledger.apply((conflicting,))
        self.assertEqual(ledger.get("bakery", "npc-1").total_delay_minutes, 12)

    def test_unknown_event_types_are_ignored_without_being_claimed_processed(self):
        other = self.events.append(WorldEventLedger.make_event("weather", 3, "weather"))
        ledger = RoutineInstitutionLedger()
        self.assertEqual(ledger.apply((other,)), ())
        self.assertEqual(ledger.processed_event_ids(), ())


if __name__ == "__main__":
    unittest.main()
