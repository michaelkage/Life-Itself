import unittest

from simreality import (
    PersonalRoutePlanner, RouteEdge, RoutineBlock, RoutineBook,
    RoutineTravelAdapter, TravelTickAdapter, TravelSnapshot,
)
from simreality.world_events import WorldEventLedger


class RoutineTravelAdapterTests(unittest.TestCase):
    def setUp(self):
        self.edges = (RouteEdge("home-office", "home", "office", 2),)
        self.planner = PersonalRoutePlanner(self.edges)
        self.travel = TravelTickAdapter(self.edges)
        self.adapter = RoutineTravelAdapter(self.travel)
        self.book = RoutineBook((
            RoutineBlock("work-shift", "npc-1", "work", "office", 540, 600),
            RoutineBlock("sleep", "npc-1", "sleep", "home", 1320, 1439),
        ))

    def test_active_routine_starts_persistent_journey(self):
        requests = self.adapter.start_due(10, self.book, 550, {"npc-1": "home"}, self.planner)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].status, "travelling")
        journey = self.travel.ledger.get(requests[0].journey_id)
        self.assertEqual(journey.routine_id, "work-shift")
        self.assertEqual(journey.destination, "office")

    def test_same_tick_request_is_idempotent_and_arrival_keeps_routine_id(self):
        first = self.adapter.start_due(10, self.book, 550, {"npc-1": "home"}, self.planner)
        second = self.adapter.start_due(10, self.book, 550, {"npc-1": "home"}, self.planner)
        self.assertEqual(first, second)
        events = WorldEventLedger()
        result = self.travel.advance(11, {"npc-1": 2}, events=events)
        self.assertEqual(result.arrivals, (first[0].journey_id,))
        event = events.get(f"travel-arrival:{first[0].journey_id}")
        self.assertEqual(dict(event.attributes)["routine_id"], "work-shift")

    def test_routine_travel_survives_snapshot_round_trip(self):
        request = self.adapter.start_due(10, self.book, 550, {"npc-1": "home"}, self.planner)[0]
        self.travel.advance(11, {"npc-1": 1})
        restored = TravelSnapshot.from_json(
            TravelSnapshot.capture(self.travel.ledger).to_json()
        ).restore()
        journey = restored.get(request.journey_id)
        self.assertEqual(journey.routine_id, "work-shift")
        self.assertEqual(journey.edge_progress, 1)

    def test_already_at_destination_and_active_other_journey_are_not_duplicated(self):
        at_destination = self.adapter.start_due(
            10, self.book, 550, {"npc-1": "office"}, self.planner,
        )
        self.assertEqual(at_destination[0].status, "already_at_destination")
        self.adapter.start_due(10, self.book, 550, {"npc-1": "home"}, self.planner)
        other = self.adapter.start_due(11, self.book, 550, {"npc-1": "home"}, self.planner)
        self.assertEqual(other[0].status, "already_travelling")

    def test_only_active_routines_are_considered_and_missing_origin_rejected(self):
        self.assertEqual(
            self.adapter.start_due(10, self.book, 700, {"npc-1": "home"}, self.planner),
            (),
        )
        with self.assertRaisesRegex(ValueError, "missing current location"):
            self.adapter.start_due(10, self.book, 550, {}, self.planner)

    def test_explicit_departure_lead_starts_before_routine_window(self):
        requests = self.adapter.start_due(
            9, self.book, 530, {"npc-1": "home"}, self.planner,
            departure_lead_minutes=15,
        )
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].routine_id, "work-shift")


if __name__ == "__main__":
    unittest.main()
