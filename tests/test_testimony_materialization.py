import unittest

from simreality.testimony import TestimonyLedger
from simreality.testimony_inquiries import (
    TestimonyInquiry, TestimonyInquiryLedger, TestimonyResponse,
)
from simreality.testimony_materialization import TestimonyMaterializationAdapter


class TestimonyMaterializationAdapterTests(unittest.TestCase):
    def setUp(self):
        self.inquiries = TestimonyInquiryLedger((
            TestimonyInquiry("q1", "event-1", "witness-1", "coat", 10),
        ))
        self.testimony = TestimonyLedger()
        self.adapter = TestimonyMaterializationAdapter()

    def test_answer_materializes_and_exact_replay_is_idempotent(self):
        self.inquiries.append_response(TestimonyResponse("q1", 12, True, "blue", 0.8))
        first = self.adapter.materialize(
            self.inquiries, self.testimony, "q1", "testimony-q1", 3.0,
        )
        second = self.adapter.materialize(
            self.inquiries, self.testimony, "q1", "testimony-q1", 3.0,
        )
        self.assertEqual(first, second)
        self.assertEqual(self.testimony.snapshot(), (first,))
        self.assertEqual(first.details[0].value, "blue")

    def test_unanswered_or_refused_inquiry_does_not_create_testimony(self):
        self.assertIsNone(self.adapter.materialize(
            self.inquiries, self.testimony, "q1", "t1", 1.0,
        ))
        self.inquiries.append_response(TestimonyResponse("q1", 11, False, None, 0.0))
        self.assertIsNone(self.adapter.materialize(
            self.inquiries, self.testimony, "q1", "t1", 1.0,
        ))
        self.assertEqual(self.testimony.snapshot(), ())

    def test_conflicting_materialization_replay_is_rejected(self):
        self.inquiries.append_response(TestimonyResponse("q1", 12, True, "blue", 0.8))
        self.adapter.materialize(self.inquiries, self.testimony, "q1", "t1", 3.0)
        with self.assertRaises(ValueError):
            self.adapter.materialize(self.inquiries, self.testimony, "q1", "t1", 4.0)

    def test_invalid_ledgers_rejected(self):
        with self.assertRaises(TypeError):
            self.adapter.materialize(object(), self.testimony, "q1", "t1", 1.0)


if __name__ == "__main__":
    unittest.main()
