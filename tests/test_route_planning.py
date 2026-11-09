import unittest

from simreality.memory_routines import RoutineAvoidanceProfile
from simreality.route_planning import PersonalRoutePlanner, RouteEdge


class PersonalRoutePlannerTests(unittest.TestCase):
    def setUp(self):
        self.planner = PersonalRoutePlanner((
            RouteEdge("a", "home", "alley", 1),
            RouteEdge("b", "alley", "market", 1),
            RouteEdge("c", "home", "main-road", 2),
            RouteEdge("d", "main-road", "market", 2),
        ))

    def test_avoids_remembered_location_for_affected_npc(self):
        profile = RoutineAvoidanceProfile("npc-1", "alley", 0.9, (0,), "main-road")
        affected = self.planner.plan("npc-1", "home", "market", avoidance_profiles=(profile,))
        unaffected = self.planner.plan("npc-2", "home", "market", avoidance_profiles=(profile,))
        self.assertEqual(affected.path, ("home", "main-road", "market"))
        self.assertEqual(affected.avoided_locations, ("alley",))
        self.assertEqual(unaffected.path, ("home", "alley", "market"))
        self.assertEqual(affected.base_cost, 4)
        self.assertGreater(affected.adjusted_cost, affected.base_cost)

    def test_deterministic_equal_cost_tie_and_edge_order(self):
        edges = (
            RouteEdge("z", "home", "b", 1),
            RouteEdge("y", "b", "goal", 1),
            RouteEdge("a", "home", "a", 1),
            RouteEdge("x", "a", "goal", 1),
        )
        first = PersonalRoutePlanner(edges).plan("npc", "home", "goal")
        second = PersonalRoutePlanner(tuple(reversed(edges))).plan("npc", "home", "goal")
        self.assertEqual(first, second)
        self.assertEqual(first.path, ("home", "a", "goal"))

    def test_unreachable_and_same_location(self):
        planner = PersonalRoutePlanner((RouteEdge("one", "a", "b", 1),))
        self.assertFalse(planner.plan("npc", "a", "missing").found)
        self.assertEqual(planner.plan("npc", "a", "a").path, ("a",))

    def test_invalid_edges_and_penalties_are_rejected(self):
        with self.assertRaises(ValueError):
            RouteEdge("bad", "a", "b", 0)
        with self.assertRaises(ValueError):
            PersonalRoutePlanner((RouteEdge("x", "a", "b", 1), RouteEdge("x", "b", "c", 1)))
        with self.assertRaises(ValueError):
            self.planner.plan("npc", "home", "market", avoidance_penalty_scale=-1)

    def test_closed_edges_are_excluded_from_personal_route(self):
        planner = PersonalRoutePlanner((
            RouteEdge("fast-a", "home", "junction", 1),
            RouteEdge("fast-b", "junction", "office", 1),
            RouteEdge("slow-a", "home", "detour", 3),
            RouteEdge("slow-b", "detour", "office", 3),
        ))
        plan = planner.plan("npc", "home", "office", closed_edge_ids=("fast-b",))
        self.assertEqual(plan.path, ("home", "detour", "office"))
        with self.assertRaises(ValueError):
            planner.plan("npc", "home", "office", closed_edge_ids=("unknown",))


if __name__ == "__main__":
    unittest.main()
