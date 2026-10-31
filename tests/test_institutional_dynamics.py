import unittest

from simreality.institutional_dynamics import (
    DepartmentState,
    InstitutionalDecisionEvaluator,
    InstitutionalDecisionOption,
    InstitutionalEmployee,
    InstitutionalProfile,
)


class InstitutionalDecisionTests(unittest.TestCase):
    def setUp(self):
        self.institution = InstitutionalProfile(
            "city_hall", "mayor",
            (("public_safety", 0.8), ("public_service", 0.6)),
            accountability=0.8, political_pressure=0.7,
            budget_pressure=0.5, staffing_pressure=0.6,
        )
        self.department = DepartmentState(
            "permits", (("public_service", 0.9),),
            budget_remaining=100, staff_available=4, influence=0.8,
        )
        self.employee = InstitutionalEmployee(
            "clerk", integrity=0.8, ambition=0.3,
            leadership_loyalty=0.4, favouritism=0.5,
            bias_weights=(("connected", 0.2), ("outsider", -0.4)),
        )
        self.evaluator = InstitutionalDecisionEvaluator()

    def option(self, option_id, **kwargs):
        defaults = dict(
            department_id="permits", description=option_id,
            budget_cost=10, staff_cost=1,
            priority_tags=("public_service",),
            evidence_strength=0.8, minimum_evidence=0.5,
            requester_influence=0.5, public_visibility=0.5,
            transparency=0.8, personal_advantage=0.1,
        )
        defaults.update(kwargs)
        return InstitutionalDecisionOption(option_id, **defaults)

    def test_deterministic_ranking_and_tie_break(self):
        options = (self.option("z"), self.option("a"))
        first = self.evaluator.evaluate(self.institution, self.department, self.employee, options)
        second = self.evaluator.evaluate(self.institution, self.department, self.employee, options)
        self.assertEqual(first, second)
        self.assertEqual([x.option_id for x in first.ranked_options], ["a", "z"])

    def test_insufficient_budget_makes_option_infeasible(self):
        result = self.evaluator.evaluate(
            self.institution, self.department, self.employee,
            (self.option("expensive", budget_cost=101), self.option("affordable")),
        )
        by_id = {item.option_id: item for item in result.ranked_options}
        self.assertFalse(by_id["expensive"].feasible)
        self.assertIn("department budget is insufficient", by_id["expensive"].blockers)
        self.assertTrue(by_id["affordable"].feasible)
        self.assertEqual(result.ranked_options[0].option_id, "affordable")

    def test_staff_shortage_is_explicit_blocker(self):
        result = self.evaluator.evaluate(
            self.institution, self.department, self.employee,
            (self.option("needs_staff", staff_cost=5),),
        )
        self.assertIn("department staffing is insufficient", result.ranked_options[0].blockers)

    def test_evidence_threshold_blocks_option(self):
        result = self.evaluator.evaluate(
            self.institution, self.department, self.employee,
            (self.option("unsupported", evidence_strength=0.2, minimum_evidence=0.7),),
        )
        self.assertFalse(result.ranked_options[0].feasible)
        self.assertIn("minimum evidence threshold is not met", result.ranked_options[0].blockers)

    def test_bias_cues_can_help_or_hurt(self):
        connected = self.option("connected", bias_cues=("connected",))
        outsider = self.option("outsider", bias_cues=("outsider",))
        result = self.evaluator.evaluate(
            self.institution, self.department, self.employee, (connected, outsider),
        )
        by_id = {item.option_id: item for item in result.ranked_options}
        def bias_amount(item):
            return next(c.amount for c in item.contributions if c.axis == "employee_bias")
        self.assertAlmostEqual(bias_amount(by_id["connected"]), 0.2)
        self.assertAlmostEqual(bias_amount(by_id["outsider"]), -0.4)

    def test_favouritism_amplifies_influence_only_when_configured(self):
        option = self.option("favoured", requester_influence=1.0)
        favoured = self.evaluator.evaluate(
            self.institution, self.department, self.employee, (option,),
        ).ranked_options[0]
        neutral_employee = InstitutionalEmployee("neutral", favouritism=0.0)
        neutral = self.evaluator.evaluate(
            self.institution, self.department, neutral_employee, (option,),
        ).ranked_options[0]
        favoured_score = next(c.amount for c in favoured.contributions if c.axis == "preferential_access")
        neutral_score = next(c.amount for c in neutral.contributions if c.axis == "preferential_access")
        self.assertGreater(favoured_score, neutral_score)

    def test_department_and_leadership_priorities_both_matter(self):
        option = self.option("service", priority_tags=("public_service",))
        result = self.evaluator.evaluate(
            self.institution, self.department, self.employee, (option,),
        ).ranked_options[0]
        priority = next(c.amount for c in result.contributions if c.axis == "priority_alignment")
        self.assertAlmostEqual(priority, 0.75)

    def test_zero_capacity_does_not_divide_by_zero(self):
        department = DepartmentState("permits", (), 0, 0)
        result = self.evaluator.evaluate(
            self.institution, department, self.employee,
            (self.option("no_capacity", budget_cost=1, staff_cost=1),),
        )
        self.assertFalse(result.ranked_options[0].feasible)
        self.assertTrue(all(c.amount == c.amount for c in result.ranked_options[0].contributions))

    def test_duplicate_option_ids_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(
                self.institution, self.department, self.employee,
                (self.option("same"), self.option("same")),
            )

    def test_wrong_department_rejected(self):
        with self.assertRaises(ValueError):
            self.evaluator.evaluate(
                self.institution, self.department, self.employee,
                (self.option("other", department_id="police"),),
            )

    def test_invalid_signed_bias_weight_rejected(self):
        with self.assertRaises(ValueError):
            InstitutionalEmployee("bad", bias_weights=(("cue", 1.1),))

    def test_invalid_profile_values_rejected(self):
        with self.assertRaises(ValueError):
            InstitutionalProfile("x", "y", (), accountability=1.5)


if __name__ == "__main__":
    unittest.main()
