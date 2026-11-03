import unittest

from simreality.testimony import TestimonyLedger
from simreality.testimony_analysis import TestimonyAnalyzer
from simreality.witness_recall import RecalledDetail, WitnessRecall


class TestimonyAnalyzerTests(unittest.TestCase):
    def record(self, testimony_id, witness_id, value, hour=0.0, decay=0.1):
        recall = WitnessRecall(
            "event-1", witness_id, 12,
            (RecalledDetail("detail-" + witness_id, "vehicle_color", value, 0.9),),
            (),
        )
        return TestimonyLedger.from_recall(
            testimony_id, recall, hour, decay_rate_per_hour=decay
        )

    def test_reports_conflict_and_corroboration_separately(self):
        ledger = TestimonyLedger((
            self.record("a1", "alice", "blue"),
            self.record("b1", "bob", "red"),
            self.record("c1", "cara", "blue"),
        ))
        report = TestimonyAnalyzer().analyze(ledger, "event-1", 2.0)
        self.assertEqual(len(report.contradictions), 2)
        self.assertEqual(len(report.corroborations), 1)
        self.assertEqual(report.corroborations[0].values, ("blue", "blue"))
        self.assertEqual(report.contradictions[0].witness_ids, ("alice", "bob"))

    def test_omission_is_not_a_conflict_and_same_witness_is_not_compared(self):
        first = self.record("a1", "alice", "blue")
        repeated = self.record("a2", "alice", "red")
        ledger = TestimonyLedger((first, repeated))
        report = TestimonyAnalyzer().analyze(ledger, "event-1", 1.0)
        self.assertEqual(report.contradictions, ())
        self.assertEqual(report.corroborations, ())

    def test_confidence_decays_without_erasing_conflict(self):
        ledger = TestimonyLedger((
            self.record("a1", "alice", "blue"),
            self.record("b1", "bob", "red"),
        ))
        early = TestimonyAnalyzer().analyze(ledger, "event-1", 1.0)
        late = TestimonyAnalyzer().analyze(ledger, "event-1", 20.0)
        self.assertEqual(len(early.contradictions), 1)
        self.assertEqual(len(late.contradictions), 1)
        self.assertLess(late.contradictions[0].confidence[0], early.contradictions[0].confidence[0])

    def test_inquiry_before_account_time_rejected(self):
        ledger = TestimonyLedger((self.record("a1", "alice", "blue", hour=3.0),))
        with self.assertRaises(ValueError):
            TestimonyAnalyzer().analyze(ledger, "event-1", 2.0)

    def test_deterministic_across_insertion_order(self):
        a = self.record("a1", "alice", "blue")
        b = self.record("b1", "bob", "red")
        c = self.record("c1", "cara", "blue")
        analyzer = TestimonyAnalyzer()
        self.assertEqual(
            analyzer.analyze(TestimonyLedger((a, b, c)), "event-1", 4.0),
            analyzer.analyze(TestimonyLedger((c, a, b)), "event-1", 4.0),
        )


if __name__ == "__main__":
    unittest.main()
