import unittest

from simreality.route_planning import PersonalRoutePlanner, RouteEdge
from simreality.travel import TravelLedger, TravelTickAdapter
from simreality.travel_save_state import TravelSnapshot
from simreality.world_events import WorldEventLedger


class TravelTickTests(unittest.TestCase):
    def setUp(self):
        self.edges = (
            RouteEdge("home-road", "home", "crossroads", 3),
            RouteEdge("market-road", "crossroads", "market", 4),
        )
        self.planner = PersonalRoutePlanner(self.edges)
        self.adapter = TravelTickAdapter(self.edges)
        self.plan = self.planner.plan("npc-1", "home", "market")
        self.adapter.start("trip-1", "npc-1", self.plan, 0)

    def test_travel_consumes_explicit_budget_over_multiple_ticks(self):
        first = self.adapter.advance(1, {"npc-1": 2})
        self.assertEqual(first.journeys[0].current_location, "home")
        self.assertEqual(first.journeys[0].edge_progress, 2)
        second = self.adapter.advance(2, {"npc-1": 3})
        self.assertEqual(second.journeys[0].current_location, "crossroads")
        self.assertEqual(second.journeys[0].edge_progress, 2)
        third = self.adapter.advance(3, {"npc-1": 2})
        self.assertEqual(third.arrivals, ())
        fourth = self.adapter.advance(4, {"npc-1": 1})
        self.assertEqual(fourth.arrivals, ("trip-1",))
        self.assertEqual(self.adapter.ledger.get("trip-1").status, "arrived")

    def test_closure_pauses_and_can_be_reopened(self):
        result = self.adapter.advance(1, {"npc-1": 5}, closed_edge_ids=("home-road",))
        self.assertEqual(result.blocked, ("trip-1",))
        self.assertEqual(self.adapter.ledger.get("trip-1").edge_progress, 0)
        self.adapter.reopen("trip-1")
        result = self.adapter.advance(2, {"npc-1": 3})
        self.assertEqual(result.journeys[0].current_location, "crossroads")

    def test_dynamic_time_multiplier_and_arrival_event(self):
        events = WorldEventLedger()
        result = self.adapter.advance(1, {"npc-1": 3}, time_multipliers={"home-road": 2})
        self.assertEqual(result.journeys[0].edge_progress, 1.5)
        arrived = self.adapter.advance(2, {"npc-1": 5.5}, events=events)
        self.assertEqual(arrived.arrivals, ("trip-1",))
        event = events.get("travel-arrival:trip-1")
        self.assertEqual(event.event_type, "npc_arrived")
        self.assertEqual(event.participants, ("npc-1",))

    def test_replay_is_idempotent_and_conflicts_rejected(self):
        first = self.adapter.advance(1, {"npc-1": 1})
        self.assertEqual(self.adapter.advance(1, {"npc-1": 1}), first)
        with self.assertRaises(ValueError):
            self.adapter.advance(1, {"npc-1": 2})

    def test_no_budget_does_not_move_and_unknown_edges_rejected(self):
        result = self.adapter.advance(1, {"npc-1": 0})
        self.assertEqual(result.journeys[0].elapsed_cost, 0)
        with self.assertRaises(ValueError):
            self.adapter.advance(2, {"npc-1": 1}, closed_edge_ids=("missing",))

    def test_same_location_journey_arrives_immediately(self):
        plan = self.planner.plan("npc-2", "home", "home")
        journey = self.adapter.start("trip-2", "npc-2", plan, 0)
        self.assertEqual(journey.status, "arrived")

    def test_snapshot_restores_partial_progress_and_tick_replay(self):
        original = self.adapter.advance(1, {"npc-1": 1})
        encoded = TravelSnapshot.capture(self.adapter.ledger).to_json()
        restored_ledger = TravelSnapshot.from_json(encoded).restore()
        restored = TravelTickAdapter(self.edges, restored_ledger)
        self.assertEqual(restored.ledger.get("trip-1").edge_progress, 1)
        self.assertEqual(restored.advance(1, {"npc-1": 1}), original)
        result = restored.advance(2, {"npc-1": 2})
        self.assertEqual(result.journeys[0].edge_progress, 0)
        self.assertEqual(result.journeys[0].current_location, "crossroads")

    def test_snapshot_rejects_noncanonical_json(self):
        encoded = TravelSnapshot.capture(self.adapter.ledger).to_json()
        with self.assertRaises(ValueError):
            TravelSnapshot.from_json(encoded + " ")

    def test_arrival_event_can_be_materialized_on_replay(self):
        self.adapter.advance(1, {"npc-1": 7})
        events = WorldEventLedger()
        replay = self.adapter.advance(1, {"npc-1": 7}, events=events)
        self.assertEqual(replay.arrivals, ("trip-1",))
        self.assertEqual(events.get("travel-arrival:trip-1").event_type, "npc_arrived")

    def test_blocked_journey_replans_at_next_junction(self):
        edges = (
            RouteEdge("home-junction", "home", "junction", 1),
            RouteEdge("junction-destination", "junction", "destination", 1),
            RouteEdge("junction-detour", "junction", "detour", 2),
            RouteEdge("detour-destination", "detour", "destination", 2),
        )
        planner = PersonalRoutePlanner(edges)
        adapter = TravelTickAdapter(edges)
        adapter.start("detour-trip", "npc-detour",
                      planner.plan("npc-detour", "home", "destination"), 0)
        first = adapter.advance(1, {"npc-detour": 2},
                                closed_edge_ids=("junction-destination",))
        self.assertEqual(first.blocked, ("detour-trip",))
        self.assertEqual(first.journeys[0].current_location, "junction")
        second = adapter.advance(2, {"npc-detour": 2},
                                 closed_edge_ids=("junction-destination",),
                                 route_planner=planner, replan_blocked=True)
        self.assertEqual(second.journeys[0].path,
                         ("home", "junction", "detour", "destination"))
        self.assertEqual(second.journeys[0].current_location, "detour")
        self.assertEqual(second.journeys[0].status, "travelling")

    def test_unreachable_journey_can_recover_when_road_reopens(self):
        edges = (RouteEdge("only-road", "home", "destination", 2),)
        planner = PersonalRoutePlanner(edges)
        adapter = TravelTickAdapter(edges)
        adapter.start("recovery-trip", "npc-recovery",
                      planner.plan("npc-recovery", "home", "destination"), 0)
        blocked = adapter.advance(1, {"npc-recovery": 1},
                                  closed_edge_ids=("only-road",),
                                  route_planner=planner, replan_blocked=True)
        self.assertEqual(blocked.journeys[0].status, "blocked")
        unreachable = adapter.advance(2, {"npc-recovery": 0},
                                       closed_edge_ids=("only-road",),
                                       route_planner=planner, replan_blocked=True)
        self.assertEqual(unreachable.journeys[0].status, "unreachable")
        recovered = adapter.advance(3, {"npc-recovery": 2},
                                    route_planner=planner, replan_blocked=True)
        self.assertEqual(recovered.arrivals, ("recovery-trip",))

    def test_replanning_inputs_participate_in_tick_replay_signature(self):
        edges = (RouteEdge("only-road", "home", "destination", 2),)
        planner = PersonalRoutePlanner(edges)
        adapter = TravelTickAdapter(edges)
        adapter.start("signature-trip", "npc-signature",
                      planner.plan("npc-signature", "home", "destination"), 0)
        adapter.advance(1, {"npc-signature": 0}, route_planner=planner,
                        replan_blocked=True)
        with self.assertRaises(ValueError):
            adapter.advance(1, {"npc-signature": 0}, route_planner=planner,
                            replan_blocked=False)


if __name__ == "__main__":
    unittest.main()
