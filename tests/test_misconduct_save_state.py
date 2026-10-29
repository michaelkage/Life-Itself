import json
import unittest

from simreality import (
    MisconductReport, MisconductReportingSystem, MisconductType,
    ReviewDecision, ReviewOutcome, WorldEventLedger,
)
from simreality.misconduct_save_state import MisconductSnapshot


class MisconductSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger((
            WorldEventLedger.make_event(
                "incident-1", 4, "police_stop",
                participants=("citizen-1", "officer-1"),
            ),
        ))
        report = MisconductReport(
            "report-1", 5, "citizen-1", "officer-1", "police-east",
            MisconductType.ABUSE_OF_AUTHORITY, ("incident-1",),
            "The stop exceeded policy.", False,
        )
        first = ReviewDecision(
            "decision-1", "report-1", 6, "reviewer-1",
            ReviewOutcome.UNDER_REVIEW, ("dispatch-log-1",),
            "Collecting available records.",
        )
        second = ReviewDecision(
            "decision-2", "report-1", 9, "reviewer-2",
            ReviewOutcome.INSUFFICIENT_EVIDENCE, ("dispatch-log-1",),
            "Available evidence does not resolve the allegation.",
        )
        self.system = MisconductReportingSystem((report,), (first, second))

    def test_round_trip_preserves_report_and_review_history(self):
        payload = MisconductSnapshot.capture(self.system).to_json()
        restored_snapshot = MisconductSnapshot.from_json(payload)
        restored = restored_snapshot.restore(self.events)
        self.assertEqual(restored.snapshot(), self.system.snapshot())
        self.assertEqual(restored.status("report-1").outcome, ReviewOutcome.INSUFFICIENT_EVIDENCE)
        self.assertEqual(
            MisconductSnapshot.capture(restored).to_json(),
            payload,
        )

    def test_restore_rejects_missing_incident_reference(self):
        payload = json.loads(MisconductSnapshot.capture(self.system).to_json())
        payload["reports"][0]["incident_ids"] = ["missing-event"]
        snapshot = MisconductSnapshot.from_json(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "missing world events"):
            snapshot.restore(self.events)

    def test_unknown_schema_and_invalid_decision_history_rejected(self):
        with self.assertRaises(ValueError):
            MisconductSnapshot.from_json('{"schema_version":99}')
        payload = json.loads(MisconductSnapshot.capture(self.system).to_json())
        payload["decisions"][1]["tick"] = 4
        with self.assertRaises(ValueError):
            MisconductSnapshot.from_json(json.dumps(payload))

    def test_snapshot_rejects_noncanonical_report_order(self):
        payload = json.loads(MisconductSnapshot.capture(self.system).to_json())
        payload["reports"].append(dict(payload["reports"][0], report_id="report-2"))
        with self.assertRaises(ValueError):
            MisconductSnapshot.from_json(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
