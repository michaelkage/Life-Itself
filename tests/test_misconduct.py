import unittest

from simreality.misconduct import (
    MisconductReport, MisconductReportingSystem, MisconductType,
    ReviewDecision, ReviewOutcome,
)


class MisconductReportingSystemTests(unittest.TestCase):
    def report(self, report_id="report-1", **overrides):
        values = dict(
            report_id=report_id, filed_tick=5, reporter_id="citizen-1",
            subject_id="officer-7", institution_id="police-east",
            misconduct_type=MisconductType.RACIAL_DISCRIMINATION,
            incident_ids=("incident-9",), description="Unequal treatment during a stop.",
        )
        values.update(overrides)
        return MisconductReport(**values)

    def decision(self, decision_id="decision-1", **overrides):
        values = dict(
            decision_id=decision_id, report_id="report-1", tick=8,
            reviewer_id="reviewer-2", outcome=ReviewOutcome.UNDER_REVIEW,
            evidence_ids=("bodycam-clip-1",), rationale="Evidence collection has started.",
        )
        values.update(overrides)
        return ReviewDecision(**values)

    def test_filing_is_not_a_finding_of_guilt(self):
        system = MisconductReportingSystem((self.report(),))
        status = system.status("report-1")
        self.assertEqual(status.outcome, ReviewOutcome.FILED)
        self.assertIsNone(status.latest_decision)

    def test_explicit_review_history_and_idempotent_replay(self):
        system = MisconductReportingSystem((self.report(),))
        first = self.decision()
        system.add_decision(first)
        system.add_decision(first)
        final = self.decision(
            "decision-2", tick=10, outcome=ReviewOutcome.SUBSTANTIATED,
            evidence_ids=("bodycam-clip-1", "dispatch-log-4"),
            rationale="Independent evidence supports the allegation.",
        )
        system.add_decision(final)
        status = system.status("report-1")
        self.assertEqual(status.outcome, ReviewOutcome.SUBSTANTIATED)
        self.assertEqual(len(status.decision_history), 2)
        self.assertEqual(system.snapshot()[1], (first, final))

    def test_unsubstantiated_and_insufficient_are_distinct(self):
        system = MisconductReportingSystem((self.report(),))
        system.add_decision(self.decision(outcome=ReviewOutcome.INSUFFICIENT_EVIDENCE))
        self.assertEqual(system.status("report-1").outcome, ReviewOutcome.INSUFFICIENT_EVIDENCE)
        system.add_decision(self.decision(
            "decision-2", tick=9, outcome=ReviewOutcome.NOT_SUBSTANTIATED,
            rationale="Available evidence did not support the allegation.",
        ))
        self.assertEqual(system.status("report-1").outcome, ReviewOutcome.NOT_SUBSTANTIATED)

    def test_anonymous_report_does_not_store_reporter_identity(self):
        report = self.report(reporter_id=None, anonymous=True)
        self.assertIsNone(report.reporter_id)
        with self.assertRaises(ValueError):
            self.report(anonymous=True)

    def test_conflicting_reuse_and_unknown_report_are_rejected(self):
        system = MisconductReportingSystem((self.report(),))
        with self.assertRaises(ValueError):
            system.add_report(self.report(description="Different allegation"))
        with self.assertRaises(ValueError):
            system.add_decision(self.decision(report_id="missing"))
        with self.assertRaises(ValueError):
            system.add_decision(self.decision(tick=4))

    def test_decision_batch_is_atomic_and_time_is_monotonic(self):
        system = MisconductReportingSystem((self.report(),))
        valid = self.decision()
        invalid = self.decision("too-early", tick=4)
        with self.assertRaises(ValueError):
            system.add_decisions((valid, invalid))
        self.assertEqual(system.snapshot()[1], ())
        system.add_decision(valid)
        with self.assertRaises(ValueError):
            system.add_decision(self.decision("older", tick=7))


if __name__ == "__main__":
    unittest.main()
