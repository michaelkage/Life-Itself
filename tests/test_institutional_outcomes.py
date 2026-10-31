import unittest

from simreality.institutional_outcomes import (
    InstitutionalOutcome,
    InstitutionalOutcomeAdapter,
    InstitutionalOutcomePolicy,
    InstitutionalOutcomeRule,
)
from simreality.institutional_politics import InstitutionalPoliticalLedger


class InstitutionalOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.ledger = InstitutionalPoliticalLedger(
            "city_hall",
            initial_influence=(("planning", 0.5), ("works", 0.5)),
            leadership_priorities=(("public_safety", 0.4),),
        )
        self.adapter = InstitutionalOutcomeAdapter()

    def test_allegation_does_not_change_state_without_explicit_rule(self):
        outcome = InstitutionalOutcome(
            "complaint-1", "city_hall", 1, "public_complaint", "alleged", "works",
            evidence_ids=("witness-statement-1",),
        )
        policy = InstitutionalOutcomePolicy("accountability-v1", ())
        assessment = self.adapter.assess(self.ledger, outcome, policy)
        self.assertFalse(assessment.applied)
        before = self.ledger.state()
        after = self.adapter.commit(self.ledger, (assessment,))
        self.assertEqual(before.department_influence, after.department_influence)
        self.assertEqual(before.leadership_priorities, after.leadership_priorities)

    def test_substantiated_complaint_can_reduce_influence_and_raise_priority(self):
        outcome = InstitutionalOutcome(
            "complaint-2", "city_hall", 2, "public_complaint", "substantiated",
            "works", priority_tag="public_safety", evidence_ids=("audit-7", "recording-2"),
        )
        policy = InstitutionalOutcomePolicy("accountability-v1", (
            InstitutionalOutcomeRule(
                "public_complaint", "substantiated", influence_delta=-0.2,
                leadership_priority_delta=0.15, priority_tag="public_safety",
            ),
        ))
        assessment = self.adapter.assess(self.ledger, outcome, policy)
        state = self.adapter.commit(self.ledger, (assessment,))
        self.assertAlmostEqual(dict(state.department_influence)["works"], 0.3)
        self.assertAlmostEqual(dict(state.leadership_priorities)["public_safety"], 0.55)

    def test_not_substantiated_can_have_a_distinct_reputation_effect(self):
        outcome = InstitutionalOutcome(
            "complaint-3", "city_hall", 3, "scandal", "not_substantiated", "planning",
        )
        policy = InstitutionalOutcomePolicy("review-v1", (
            InstitutionalOutcomeRule("scandal", "not_substantiated", influence_delta=0.03),
        ))
        state = self.adapter.commit(self.ledger, (self.adapter.assess(self.ledger, outcome, policy),))
        self.assertAlmostEqual(dict(state.department_influence)["planning"], 0.53)

    def test_successful_project_can_build_influence_and_shift_priorities(self):
        outcome = InstitutionalOutcome(
            "project-9", "city_hall", 4, "project_success", "confirmed",
            "planning", priority_tag="public_safety",
        )
        policy = InstitutionalOutcomePolicy("delivery-v1", (
            InstitutionalOutcomeRule(
                "project_success", "confirmed", influence_delta=0.1,
                leadership_priority_delta=0.2, priority_tag="public_safety",
            ),
        ))
        state = self.adapter.commit(self.ledger, (self.adapter.assess(self.ledger, outcome, policy),))
        self.assertAlmostEqual(dict(state.department_influence)["planning"], 0.6)
        self.assertAlmostEqual(dict(state.leadership_priorities)["public_safety"], 0.6)

    def test_leadership_change_can_rebalance_department_relationship(self):
        outcome = InstitutionalOutcome(
            "leader-2", "city_hall", 5, "leadership_change", "confirmed",
            "planning", related_department_id="works",
        )
        policy = InstitutionalOutcomePolicy("succession-v1", (
            InstitutionalOutcomeRule("leadership_change", "confirmed", relationship_delta=0.35),
        ))
        state = self.adapter.commit(self.ledger, (self.adapter.assess(self.ledger, outcome, policy),))
        self.assertEqual(state.department_relationships, (("planning", "works", 0.35),))

    def test_evidence_status_is_part_of_rule_selection(self):
        rules = (
            InstitutionalOutcomeRule("scandal", "alleged", influence_delta=0.0),
            InstitutionalOutcomeRule("scandal", "substantiated", influence_delta=-0.25),
            InstitutionalOutcomeRule("scandal", "retracted", influence_delta=0.1),
        )
        policy = InstitutionalOutcomePolicy("scandal-v1", rules)
        alleged = InstitutionalOutcome("s1", "city_hall", 1, "scandal", "alleged", "works")
        substantiated = InstitutionalOutcome("s2", "city_hall", 1, "scandal", "substantiated", "works")
        retracted = InstitutionalOutcome("s3", "city_hall", 1, "scandal", "retracted", "works")
        assessments = tuple(self.adapter.assess(self.ledger, item, policy)
                            for item in (alleged, substantiated, retracted))
        self.assertEqual([x.influence_delta for x in assessments], [0.0, -0.25, 0.1])

    def test_identical_commit_is_idempotent_and_changed_policy_is_rejected(self):
        outcome = InstitutionalOutcome("same-id", "city_hall", 1, "project_success", "confirmed", "planning")
        policy = InstitutionalOutcomePolicy("p1", (
            InstitutionalOutcomeRule("project_success", "confirmed", influence_delta=0.1),
        ))
        assessment = self.adapter.assess(self.ledger, outcome, policy)
        first = self.adapter.commit(self.ledger, (assessment,))
        second = self.adapter.commit(self.ledger, (assessment,))
        self.assertEqual(first, second)
        changed_policy = InstitutionalOutcomePolicy("p2", (
            InstitutionalOutcomeRule("project_success", "confirmed", influence_delta=0.1),
        ))
        changed = self.adapter.assess(self.ledger, outcome, changed_policy)
        with self.assertRaises(ValueError):
            self.adapter.commit(self.ledger, (changed,))

    def test_relationship_and_priority_effects_require_targets(self):
        policy = InstitutionalOutcomePolicy("bad-target", (
            InstitutionalOutcomeRule("leadership_change", "confirmed", relationship_delta=0.2),
        ))
        outcome = InstitutionalOutcome("leader", "city_hall", 1, "leadership_change", "confirmed", "planning")
        with self.assertRaises(ValueError):
            self.adapter.assess(self.ledger, outcome, policy)

    def test_policy_rejects_duplicate_rules(self):
        rule = InstitutionalOutcomeRule("scandal", "substantiated", influence_delta=-0.1)
        with self.assertRaises(ValueError):
            InstitutionalOutcomePolicy("duplicate", (rule, rule))

    def test_snapshot_restores_committed_outcomes(self):
        outcome = InstitutionalOutcome("restore-me", "city_hall", 2, "project_success", "confirmed", "planning")
        policy = InstitutionalOutcomePolicy("delivery", (
            InstitutionalOutcomeRule("project_success", "confirmed", influence_delta=0.12),
        ))
        self.adapter.commit(self.ledger, (self.adapter.assess(self.ledger, outcome, policy),))
        restored = InstitutionalPoliticalLedger.from_snapshot(self.ledger.snapshot())
        self.assertEqual(restored.state(), self.ledger.state())


if __name__ == "__main__":
    unittest.main()
