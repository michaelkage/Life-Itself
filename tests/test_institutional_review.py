"""Regression tests for context-aware institutional review recommendations."""
import unittest

from simreality.routine_institution_ledger import InstitutionalRecord
from simreality.institutional_review import (
    ContextAdjustment, InstitutionalReviewEvaluator, InstitutionalReviewPolicy, ReviewLevel,
)


class InstitutionalReviewTests(unittest.TestCase):
    def setUp(self):
        self.policy = InstitutionalReviewPolicy("balanced")
        self.evaluator = InstitutionalReviewEvaluator(self.policy)

    def test_no_history_does_not_trigger_review(self):
        result = self.evaluator.assess(InstitutionalRecord("clinic", "person"))
        self.assertEqual(result.level, ReviewLevel.NONE)
        self.assertEqual(result.score, 0)

    def test_repeated_events_cross_configured_thresholds(self):
        record = InstitutionalRecord("bakery", "worker", late_arrivals=2, total_delay_minutes=120)
        result = self.evaluator.assess(record)
        self.assertEqual(result.level, ReviewLevel.FORMAL_REVIEW)
        self.assertEqual(result.score, 4.0)
        self.assertEqual(result.policy_id, "balanced")

    def test_context_can_change_assessment_without_erasing_history(self):
        record = InstitutionalRecord("bakery", "worker", late_arrivals=3)
        base = self.evaluator.assess(record)
        adjusted = self.evaluator.assess(record, (
            ContextAdjustment("bus-service", -2.5, "A documented city transit disruption affected the shift."),
        ))
        self.assertEqual(base.level, ReviewLevel.FORMAL_REVIEW)
        self.assertEqual(adjusted.level, ReviewLevel.NONE)
        self.assertEqual(record.late_arrivals, 3)
        self.assertEqual(adjusted.contributions[-1].source, "context:bus-service")

    def test_positive_context_can_raise_review_pressure_transparently(self):
        record = InstitutionalRecord("clinic", "person", missed_appointments=2)
        result = self.evaluator.assess(record, (
            ContextAdjustment("prior-notice", 1.0, "The person had already received clear written notice."),
        ))
        self.assertEqual(result.level, ReviewLevel.FORMAL_REVIEW)
        self.assertIn("not a finding of fault", result.note)

    def test_context_order_does_not_change_result(self):
        record = InstitutionalRecord("workplace", "person", late_arrivals=2)
        a = ContextAdjustment("a", -0.5, "Verified transport disruption.")
        b = ContextAdjustment("b", 0.5, "Repeated ignored contact attempts.")
        first = self.evaluator.assess(record, (a, b))
        second = self.evaluator.assess(record, (b, a))
        self.assertEqual(first, second)
        self.assertEqual(first.level, ReviewLevel.FORMAL_REVIEW)

    def test_invalid_policy_and_duplicate_context_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "thresholds must be ordered"):
            InstitutionalReviewPolicy("bad", 3, 2, 1)
        signal = ContextAdjustment("same", 0, "No adjustment.")
        with self.assertRaisesRegex(ValueError, "unique"):
            self.evaluator.assess(InstitutionalRecord("x", "y"), (signal, signal))

    def test_context_adjustment_must_be_finite(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            ContextAdjustment("nan", float("nan"), "Invalid")


if __name__ == "__main__":
    unittest.main()
