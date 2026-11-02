"""Regression tests for evidence-based, non-mutating NPC goal reviews."""
import unittest

from simreality.goal_review import (
    GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy,
)
from simreality.goals import GoalBook, NPCGoal
from simreality.world_events import WorldEventLedger


class GoalReviewEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("career", "npc-1", "career", 5.0,
                               review_tick=2, confidence=0.7))
        self.goals.add(NPCGoal("family", "npc-1", "family", 4.0))
        self.goals.add(NPCGoal("other-owner", "npc-2", "career", 8.0))
        self.event = WorldEventLedger.make_event(
            "promotion-denied", 3, "promotion_denied",
            participants=("npc-1",), attributes={"department": "engineering"},
        )

    def test_reprioritization_and_confidence_are_proposals_only(self):
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy(
                "career-setback", "promotion_denied", "career",
                GoalReviewAction.REPRIORITIZE, priority_delta=-2.0,
                confidence_delta=-0.2,
                required_attributes=(("department", "engineering"),),
            ),
        ))
        before = self.goals.snapshot()
        proposals = evaluator.assess((self.event,))
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal.goal_id, "career")
        self.assertEqual(proposal.proposed_priority, 3.0)
        self.assertAlmostEqual(proposal.proposed_confidence, 0.5)
        self.assertEqual(self.goals.snapshot(), before)

    def test_policy_can_suggest_reframing_without_changing_goal(self):
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy(
                "career-pivot", "promotion_denied", "career",
                GoalReviewAction.REFRAME, target_category="entrepreneurship",
            ),
        ))
        proposal = evaluator.assess((self.event,))[0]
        self.assertEqual(proposal.action, GoalReviewAction.REFRAME)
        self.assertEqual(proposal.current_category, "career")
        self.assertEqual(proposal.proposed_category, "entrepreneurship")
        self.assertEqual(self.goals.goals["career"].category, "career")

    def test_pause_and_abandon_are_recommendations_not_automatic_transitions(self):
        for action in (GoalReviewAction.PAUSE, GoalReviewAction.ABANDON):
            evaluator = GoalReviewEvaluator(self.goals, (
                GoalReviewPolicy(action.value, "promotion_denied", "career", action),
            ))
            proposal = evaluator.assess((self.event,))[0]
            self.assertEqual(proposal.action, action)
            self.assertEqual(self.goals.goals["career"].status.value, "active")

    def test_owner_category_confidence_and_attribute_filters(self):
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy(
                "qualified", "promotion_denied", "career",
                GoalReviewAction.PERSIST, minimum_confidence=0.8,
                required_attributes=(("department", "finance"),),
            ),
        ))
        self.assertEqual(evaluator.assess((self.event,)), ())

    def test_goal_review_tick_prevents_reviewing_with_older_evidence(self):
        old_event = WorldEventLedger.make_event(
            "old", 1, "promotion_denied", participants=("npc-1",),
        )
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy("persist", "promotion_denied", "career",
                             GoalReviewAction.PERSIST),
        ))
        self.assertEqual(evaluator.assess((old_event,)), ())

    def test_results_are_stable_and_input_order_independent(self):
        second = WorldEventLedger.make_event(
            "another", 4, "promotion_denied", participants=("npc-1",),
        )
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy("a", "promotion_denied", "career",
                             GoalReviewAction.PERSIST),
        ))
        self.assertEqual(evaluator.assess((self.event, second)),
                         evaluator.assess((second, self.event)))

    def test_duplicate_policy_ids_and_event_ids_are_rejected(self):
        policy = GoalReviewPolicy("same", "promotion_denied", "career",
                                  GoalReviewAction.PERSIST)
        with self.assertRaises(ValueError):
            GoalReviewEvaluator(self.goals, (policy, policy))
        evaluator = GoalReviewEvaluator(self.goals, (policy,))
        with self.assertRaises(ValueError):
            evaluator.assess((self.event, self.event))

    def test_invalid_reframe_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            GoalReviewPolicy("bad", "event", "career", GoalReviewAction.REFRAME)


if __name__ == "__main__":
    unittest.main()
