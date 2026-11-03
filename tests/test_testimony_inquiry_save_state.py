import unittest

from simreality.testimony_inquiries import (
    TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse,
)
from simreality.testimony_inquiry_save_state import TestimonyInquirySnapshot


class TestimonyInquirySnapshotTests(unittest.TestCase):
    def make_ledger(self):
        ledger = TestimonyInquiryLedger((
            TestimonyInquiry("q1", "evt", "alice", "coat", 4),
            TestimonyInquiry("q2", "evt", "bob", "vehicle", 5),
        ))
        ledger.append_response(TestimonyResponse("q1", 6, True, "blue", 0.9))
        ledger.append_response(TestimonyResponse("q2", 7, False, None, 0.0))
        return ledger

    def test_capture_restore_round_trip_is_canonical(self):
        snapshot = TestimonyInquirySnapshot.capture(self.make_ledger())
        encoded = snapshot.to_json()
        decoded = TestimonyInquirySnapshot.from_json(encoded)
        restored = decoded.restore()
        self.assertEqual(restored.to_json(), self.make_ledger().to_json())
        self.assertEqual(decoded.to_json(), encoded)

    def test_noncanonical_json_rejected(self):
        snapshot = TestimonyInquirySnapshot.capture(self.make_ledger())
        raw = snapshot.to_json().replace('"schema_version":1', '"schema_version": 1')
        with self.assertRaises(ValueError):
            TestimonyInquirySnapshot.from_json(raw)

    def test_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):
            TestimonyInquirySnapshot.from_json('{"schema_version":2,"ledger":{}}')


if __name__ == "__main__":
    unittest.main()
