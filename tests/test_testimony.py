import unittest

from simreality.testimony import TestimonyLedger
from simreality.witness_recall import RecallDetail, WitnessRecall, RecalledDetail


class TestimonyLedgerTests(unittest.TestCase):
    def setUp(self):
        self.recall = WitnessRecall("event-1", "witness-1", 9,
            (RecalledDetail("d1", "coat", "green", 0.8),),
            ("d2",))

    def test_decay_is_absolute_and_replay_safe(self):
        ledger = TestimonyLedger()
        record = ledger.from_recall("account-1", self.recall, 2.0, decay_rate_per_hour=0.1)
        ledger.append(record)
        self.assertAlmostEqual(record.confidence_at(record.details[0], 4.0), 0.8 * __import__("math").exp(-0.2))
        self.assertEqual(ledger.append(record), record)
        with self.assertRaises(ValueError):
            ledger.append(ledger.from_recall("account-1", self.recall, 3.0))

    def test_save_load_canonical_round_trip(self):
        record = TestimonyLedger.from_recall("account-1", self.recall, 2.0)
        ledger = TestimonyLedger((record,))
        payload = ledger.to_json()
        restored = TestimonyLedger.from_json(payload)
        self.assertEqual(restored.to_json(), payload)
        self.assertEqual(restored.get("account-1"), record)

    def test_future_time_rejected(self):
        record = TestimonyLedger.from_recall("account-1", self.recall, 2.0)
        with self.assertRaises(ValueError):
            record.confidence_at(record.details[0], 1.0)


if __name__ == "__main__":
    unittest.main()
