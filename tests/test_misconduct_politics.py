import unittest

from simreality.institutional_outcomes import (
    InstitutionalOutcomeAdapter,
    InstitutionalOutcomePolicy,
    InstitutionalOutcomeRule,
)
from simreality.institutional_politics import InstitutionalPoliticalLedger
from simreality.misconduct import (
    MisconductReport, MisconductReportingSystem, MisconductType,
    ReviewDecision, ReviewOutcome,
)
from simreality.misconduct_politics import MisconductPoliticalBridge


class MisconductPoliticalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.system = MisconductReportingSystem()
        self.report = MisconductReport(
            report_id="report-1",
            filed_tick=2,
            reporter_id="citizen-4",
            subject_id="employee-9",
            institution_id="city_hall",
            misconduct_type=MisconductType.CORRUPTION,
            incident_ids=("world-event-8",),
            description="Possible misuse of public funds",
        )
        self.system.add_report(self.report)
        self.ledger = InstitutionalPoliticalLedger(
            "city_hall", initial_influence=(("procurement", 0.6),)
        )
        self.bridge = MisconductPoliticalBridge(InstitutionalOutcomeAdapter())

    def test_filing_is_only_an_allegation_and_has_no_implicit_effect(self):
        policy = InstitutionalOutcomePolicy("no-allegation-penalty", ())
        status = self.system.status("report-1")
        assessments = self.bridge.assess_status(
            self.ledger, status, department_id="procurement", policy=policy
        )
        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0].event.rationale.split(";")[2], "finding:alleged")
        before = self.ledger.state()
        after = self.bridge.commit(self.ledger, assessments)
        self.assertEqual(before.department_influence, after.department_influence)

    def test_review_decisions_map_to_distinct_policy_findings(self):
        self.system.add_decision(ReviewDecision(
            "decision-1", "report-1", 4, "reviewer-a",
            ReviewOutcome.SUBSTANTIATED, ("audit-2",), "Records corroborate the report",
        ))
        self.system.add_decision(ReviewDecision(
            "decision-2", "report-1", 6, "reviewer-b",
            ReviewOutcome.NOT_SUBSTANTIATED, ("interview-3",), "Later review changes the finding",
        ))
        policy = InstitutionalOutcomePolicy("review-effects", (
            InstitutionalOutcomeRule("misconduct:corruption", "substantiated", influence_delta=-0.2),
            InstitutionalOutcomeRule("misconduct:corruption", "not_substantiated", influence_delta=0.05),
        ))
        assessments = self.bridge.assess_status(
            self.ledger, self.system.status("report-1"),
            department_id="procurement", policy=policy,
        )
        self.assertEqual(
            [item.event.period_index for item in assessments], [2, 4, 6]
        )
        self.assertEqual(
            [item.event.influence_delta for item in assessments], [0.0, -0.2, 0.05]
        )
        state = self.bridge.commit(self.ledger, assessments)
        self.assertAlmostEqual(dict(state.department_influence)["procurement"], 0.45)

    def test_subject_to_department_mapping_must_be_explicit(self):
        policy = InstitutionalOutcomePolicy("empty", ())
        status = self.system.status("report-1")
        with self.assertRaises(ValueError):
            self.bridge.assess_status(
                self.ledger, status, department_id="", policy=policy
            )

    def test_under_review_and_dismissed_remain_distinct(self):
        self.system.add_decision(ReviewDecision(
            "decision-review", "report-1", 3, "reviewer-a",
            ReviewOutcome.UNDER_REVIEW, (), "Review remains open",
        ))
        self.system.add_decision(ReviewDecision(
            "decision-dismissed", "report-1", 4, "reviewer-a",
            ReviewOutcome.DISMISSED, (), "Procedural dismissal",
        ))
        policy = InstitutionalOutcomePolicy("status-labels", ())
        assessments = self.bridge.assess_status(
            self.ledger, self.system.status("report-1"),
            department_id="procurement", policy=policy,
        )
        self.assertEqual(
            [item.event.rationale.split(";")[2] for item in assessments],
            ["finding:alleged", "finding:under_review", "finding:dismissed"],
        )

    def test_wrong_institution_is_rejected(self):
        other = InstitutionalPoliticalLedger("another_institution")
        with self.assertRaises(ValueError):
            self.bridge.assess_status(
                other, self.system.status("report-1"),
                department_id="procurement",
                policy=InstitutionalOutcomePolicy("empty", ()),
            )

    def test_replaying_report_history_is_idempotent(self):
        self.system.add_decision(ReviewDecision(
            "decision-3", "report-1", 5, "reviewer-a",
            ReviewOutcome.INSUFFICIENT_EVIDENCE, (), "Insufficient evidence",
        ))
        policy = InstitutionalOutcomePolicy("no-effects", ())
        assessments = self.bridge.assess_status(
            self.ledger, self.system.status("report-1"),
            department_id="procurement", policy=policy,
        )
        first = self.bridge.commit(self.ledger, assessments)
        second = self.bridge.commit(self.ledger, assessments)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
