import unittest

from simreality.institutional_resources import (
    DepartmentResourceRequest,
    InstitutionalResourceAllocator,
    ResourceAllocationPolicy,
)


class InstitutionalResourceAllocationTests(unittest.TestCase):
    def setUp(self):
        self.allocator = InstitutionalResourceAllocator()
        self.policy = ResourceAllocationPolicy("annual", 0.5, 0.25, 0.15, 0.1)
        self.priorities = (("public_safety", 0.9), ("public_service", 0.7))

    def request(self, department_id, **kwargs):
        values = dict(
            department_id=department_id, budget_requested=100, staff_requested=10,
            priority_tags=("public_service",), service_impact=0.5,
            urgency=0.2, influence=0.5,
        )
        values.update(kwargs)
        return DepartmentResourceRequest(**values)

    def plan(self, requests, budget=100, staff=10):
        return self.allocator.plan(
            "city", "year-1", budget, staff, requests, self.priorities, self.policy,
        )

    def test_deterministic_and_input_order_independent(self):
        a = self.request("a", priority_tags=("public_safety",))
        b = self.request("b", priority_tags=("public_service",))
        self.assertEqual(self.plan((a, b)), self.plan((b, a)))

    def test_higher_priority_department_gets_first_allocation(self):
        safety = self.request("safety", priority_tags=("public_safety",))
        services = self.request("services", priority_tags=("public_service",))
        result = self.plan((services, safety), budget=100, staff=10)
        self.assertEqual(result.allocations[0].department_id, "safety")
        self.assertEqual(result.allocations[0].allocation_ratio, 1.0)
        self.assertEqual(result.allocations[1].allocation_ratio, 0.0)

    def test_partial_allocation_uses_same_ratio_for_both_resources(self):
        a = self.request("a", budget_requested=100, staff_requested=10)
        result = self.plan((a,), budget=40, staff=8)
        item = result.allocations[0]
        self.assertAlmostEqual(item.allocation_ratio, 0.4)
        self.assertAlmostEqual(item.budget_allocated, 40)
        self.assertAlmostEqual(item.staff_allocated, 4)
        self.assertAlmostEqual(item.budget_unmet, 60)
        self.assertAlmostEqual(item.staff_unmet, 6)

    def test_zero_budget_or_staff_request_is_supported(self):
        budget_only = self.request("budget", budget_requested=20, staff_requested=0)
        staff_only = self.request("staff", budget_requested=0, staff_requested=2)
        result = self.plan((budget_only, staff_only), budget=20, staff=2)
        by_id = {x.department_id: x for x in result.allocations}
        self.assertEqual(by_id["budget"].budget_allocated, 20)
        self.assertEqual(by_id["staff"].staff_allocated, 2)

    def test_allocations_never_exceed_pool(self):
        requests = tuple(self.request(str(i)) for i in range(5))
        result = self.plan(requests, budget=175, staff=13)
        self.assertLessEqual(sum(x.budget_allocated for x in result.allocations), 175)
        self.assertLessEqual(sum(x.staff_allocated for x in result.allocations), 13)

    def test_stable_tie_break_by_department_id(self):
        a = self.request("a")
        b = self.request("b")
        result = self.plan((b, a), budget=100, staff=10)
        self.assertEqual(result.allocations[0].department_id, "a")

    def test_duplicate_department_request_rejected(self):
        with self.assertRaises(ValueError):
            self.plan((self.request("same"), self.request("same")))

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(ValueError):
            self.request("bad", budget_requested=-1)
        with self.assertRaises(ValueError):
            ResourceAllocationPolicy("bad", 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            self.plan((self.request("a"),), budget=float("nan"))

    def test_allocation_score_exposes_each_pressure(self):
        result = self.plan((self.request("a"),))
        self.assertEqual(
            [name for name, _ in result.allocations[0].score_contributions],
            ["leadership_priority", "service_impact", "urgency", "department_influence"],
        )


if __name__ == "__main__":
    unittest.main()
