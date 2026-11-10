import unittest

from simreality.presence import NPCPresence, PresenceLedger, PresenceTickAdapter
from simreality.travel import TravelJourney, TravelLedger
from simreality.presence_save_state import PresenceSnapshot
from simreality.world_events import WorldEventLedger


class PresenceTests(unittest.TestCase):
    def test_explicit_placement_and_occupancy_queries(self):
        ledger = PresenceLedger()
        ledger.place("a", "market", 0)
        ledger.place("b", "market", 0)
        ledger.place("c", "home", 0)
        self.assertEqual(ledger.occupants("market"), ("a", "b"))
        self.assertEqual(ledger.occupants("home"), ("c",))

    def test_travel_sync_tracks_exact_edge_and_partial_progress(self):
        ledger = PresenceLedger()
        ledger.place("npc", "home", 0)
        travel = TravelLedger((TravelJourney(
            "j", "npc", "home", "office", ("home", "office"), ("road",),
            edge_progress=0.4, elapsed_cost=0.4, status="travelling", started_tick=1,
        ),))
        events = WorldEventLedger()
        adapter = PresenceTickAdapter(ledger)
        records = adapter.synchronize(1, travel, events=events)
        self.assertEqual(records[0].status, "travelling")
        self.assertEqual(records[0].location_id, "home")
        self.assertEqual(records[0].edge_id, "road")
        self.assertEqual(records[0].edge_progress, 0.4)
        self.assertEqual(ledger.occupants("home"), ())
        self.assertEqual(events.query(event_type="npc_presence_updated")[0].tick, 1)

    def test_arrival_restores_location_occupancy(self):
        ledger = PresenceLedger()
        ledger.place("npc", "home", 0)
        travel = TravelLedger((TravelJourney(
            "j", "npc", "home", "office", ("home", "office"), ("road",),
            edge_index=1, status="arrived", started_tick=1, arrived_tick=2,
        ),))
        PresenceTickAdapter(ledger).synchronize(2, travel)
        self.assertEqual(ledger.get("npc").location_id, "office")
        self.assertEqual(ledger.occupants("office"), ("npc",))

    def test_blocked_and_unreachable_are_not_treated_as_at_location(self):
        ledger = PresenceLedger()
        ledger.place("npc", "home", 0)
        for status in ("blocked", "unreachable"):
            travel = TravelLedger((TravelJourney(
                "j", "npc", "home", "office", ("home", "office"), ("road",),
                status=status, started_tick=1,
            ),))
            record = PresenceTickAdapter(ledger).synchronize(1 if status == "blocked" else 2, travel)[0]
            self.assertEqual(record.status, status)
            self.assertEqual(ledger.occupants("home"), ())

    def test_tick_replay_is_idempotent_and_conflicts_rejected(self):
        ledger = PresenceLedger()
        travel = TravelLedger((TravelJourney(
            "j", "npc", "a", "b", ("a", "b"), ("road",),
            status="travelling", started_tick=1,
        ),))
        adapter = PresenceTickAdapter(ledger)
        first = adapter.synchronize(1, travel)
        self.assertEqual(adapter.synchronize(1, travel), first)
        changed = TravelLedger((TravelJourney(
            "j", "npc", "a", "b", ("a", "b"), ("road",),
            edge_progress=0.5, status="travelling", started_tick=1,
        ),))
        with self.assertRaisesRegex(ValueError, "conflicting"):
            adapter.synchronize(1, changed)

    def test_cannot_relocate_an_npc_during_travel(self):
        ledger = PresenceLedger()
        ledger.place("npc", "home", 0)
        ledger._records["npc"] = NPCPresence("npc", "travelling", "home", "j", "road", 0.2, 1)
        with self.assertRaisesRegex(ValueError, "active"):
            ledger.place("npc", "office", 2)

    def test_snapshot_round_trip_preserves_replay_history(self):
        ledger = PresenceLedger()
        travel = TravelLedger((TravelJourney(
            "j", "npc", "home", "office", ("home", "office"), ("road",),
            edge_progress=0.25, status="travelling", started_tick=1,
        ),))
        PresenceTickAdapter(ledger).synchronize(1, travel)
        payload = PresenceSnapshot.capture(ledger).to_json()
        restored = PresenceSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        self.assertEqual(restored.tick_snapshot(), ledger.tick_snapshot())


if __name__ == "__main__":
    unittest.main()
