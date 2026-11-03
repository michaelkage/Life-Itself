import unittest
from simreality.testimony import TestimonyLedger
from simreality.testimony_inquiries import TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse

class TestimonyInquiryLedgerTests(unittest.TestCase):
    def test_answer_materializes_into_existing_testimony_pipeline(self):
        ledger = TestimonyInquiryLedger()
        inquiry = TestimonyInquiry("q1", "evt", "witness", "coat", 10)
        ledger.append_inquiry(inquiry)
        response = TestimonyResponse("q1", 11, True, "blue", 0.9)
        ledger.append_response(response)
        self.assertEqual(ledger.append_response(response), response)
        record = ledger.to_testimony_record("q1", "testimony-q1", 2.0)
        self.assertEqual(record.details[0].value, "blue")
        testimony = TestimonyLedger((record,))
        restored = TestimonyLedger.from_json(testimony.to_json())
        self.assertEqual(restored.snapshot(), testimony.snapshot())

    def test_refusal_is_persisted_but_not_fabricated_as_testimony(self):
        ledger = TestimonyInquiryLedger((TestimonyInquiry("q", "evt", "w", "coat", 2),))
        ledger.append_response(TestimonyResponse("q", 3, False, None, 0.0))
        self.assertIsNone(ledger.to_testimony_record("q", "t", 1.0))
        restored = TestimonyInquiryLedger.from_json(ledger.to_json())
        self.assertEqual(restored.responses(), ledger.responses())

    def test_conflicting_replay_is_rejected(self):
        ledger = TestimonyInquiryLedger((TestimonyInquiry("q", "evt", "w", "coat", 2),))
        ledger.append_response(TestimonyResponse("q", 3, True, "blue", 0.8))
        with self.assertRaises(ValueError):
            ledger.append_response(TestimonyResponse("q", 3, True, "red", 0.8))

    def test_response_before_question_is_rejected(self):
        ledger = TestimonyInquiryLedger((TestimonyInquiry("q", "evt", "w", "coat", 4),))
        with self.assertRaises(ValueError):
            ledger.append_response(TestimonyResponse("q", 3, True, "blue", 0.8))

if __name__ == "__main__":
    unittest.main()
