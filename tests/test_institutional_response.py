"""Tests for institution-specific response option planning."""
import unittest

from simreality.institutional_review import (
    InstitutionalReviewAssessment, ReviewContribution, ReviewLevel,
)
from simreality.institutional_response import (
    InstitutionalResponseOption, InstitutionalResponsePlanner, InstitutionalResponsePolicy,
)


def policy():
    return InstitutionalResponsePolicy("worker-support-v1", (
        (ReviewLevel.NONE, ()),
        (ReviewLevel.CHECK_IN, (
            InstitutionalResponseOption("private_check_in", "Offer a private, non-punitive check-in.", True),
            InstitutionalResponseOption("ask_about_barriers", "Ask whether practical barriers need attention.", True),
        )),
        (ReviewLevel.FORMAL_REVIEW, (
            InstitutionalResponseOption("fact_finding_meeting", "Hold a documented meeting and hear the person's account."),
            InstitutionalResponseOption("offer_accommodation", "Offer a chance to request a reasonable adjustment.", True),
            InstitutionalResponseOption("review_schedule", "Review whether the schedule remains workable.", True),
        )),
        (ReviewLevel.URGENT_REVIEW, (
            InstitutionalResponseOption("urgent_fact_finding", "Arrange prompt fact-finding with an opportunity to respond."),
            InstitutionalResponseOption("immediate_support", "Offer immediate practical support.", True),
        )),
    ))


class InstitutionalResponseTests(unittest.TestCase):
    def assessment(self, level):
        return InstitutionalReviewAssessment(
            "workplace", "npc-1", "review-v1", 2.0, level, (),
        )

    def test_maps_level_to_options_without_selecting_one(self):
        result = InstitutionalResponsePlanner(policy()).plan(self.assessment(ReviewLevel.FORMAL_REVIEW))
        self.assertEqual(result.response_policy_id, "worker-support-v1")
        self.assertEqual(
            tuple(item.option_id for item in result.options),
            ("fact_finding_meeting", "offer_accommodation", "review_schedule"),
        )
        self.assertIn("no action is selected", result.note)

    def test_no_review_has_no_response_options(self):
        result = InstitutionalResponsePlanner(policy()).plan(self.assessment(ReviewLevel.NONE))
        self.assertEqual(result.options, ())

    def test_supportive_options_are_explicitly_tagged(self):
        result = InstitutionalResponsePlanner(policy()).plan(self.assessment(ReviewLevel.CHECK_IN))
        self.assertTrue(all(item.supportive for item in result.options))

    def test_policy_must_cover_every_level(self):
        with self.assertRaisesRegex(ValueError, "every review level"):
            InstitutionalResponsePolicy("incomplete", ((ReviewLevel.NONE, ()),))

    def test_duplicate_option_ids_are_rejected(self):
        duplicate = InstitutionalResponseOption("same", "Option A")
        with self.assertRaisesRegex(ValueError, "unique"):
            InstitutionalResponsePolicy("bad", (
                (ReviewLevel.NONE, ()),
                (ReviewLevel.CHECK_IN, ()),
                (ReviewLevel.FORMAL_REVIEW, (duplicate, duplicate)),
                (ReviewLevel.URGENT_REVIEW, ()),
            ))

    def test_invalid_assessment_is_rejected(self):
        with self.assertRaises(TypeError):
            InstitutionalResponsePlanner(policy()).plan("not an assessment")


if __name__ == "__main__":
    unittest.main()
