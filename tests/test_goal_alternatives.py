"""Tests for explicit alternative goal formation and adoption."""
import unittest
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.npc_goal_emergence import GoalEmergenceRule, GoalLifecycleLedger, GoalTemplate
from simreality.goal_alternatives import (GoalAlternativeAdapter, GoalAlternativeEvaluator, GoalIntentionEvaluator)
from simreality.goal_review import GoalReviewAction, GoalReviewPolicy
from simreality.world_events import WorldEventLedger

class GoalAlternativeTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.source = NPCGoal("career-goal", "npc", "career", 7.0, confidence=0.8)
        self.goals.add(self.source)
        self.rules = (
            GoalEmergenceRule("seek-community", GoalTemplate("community", "social", 5.0, 0.7),
                              need_key="belonging", need_threshold=0.6),
        )
        self.lifecycle = GoalLifecycleLedger()

    def proposal(self):
        result, = GoalAlternativeEvaluator.assess(
            self.goals, "career-goal", 10, rules=self.rules,
            need_deficits={"belonging": 0.9},
        )
        return result

    def test_assessment_is_read_only_and_links_distinct_intention(self):
        before = self.goals.snapshot()
        proposal = self.proposal()
        self.assertEqual(proposal.source_goal_id, "career-goal")
        self.assertEqual(proposal.emergence.template.category, "social")
        self.assertNotEqual(proposal.proposed_goal_id, proposal.source_goal_id)
        self.assertEqual(self.goals.snapshot(), before)

    def test_adoption_adds_goal_without_overwriting_source(self):
        proposal = self.proposal()
        adopted, event = GoalAlternativeAdapter.adopt(proposal, self.goals, self.lifecycle)
        self.assertEqual(adopted.status, GoalStatus.ACTIVE)
        self.assertEqual(self.source.status, GoalStatus.ACTIVE)
        self.assertEqual(self.source.category, "career")
        self.assertEqual(event.to_status, "active")
        self.assertEqual(event.evidence_ids, proposal.evidence_ids)
        self.assertEqual(len(self.goals.goals), 2)

    def test_stale_source_rejects_adoption(self):
        proposal = self.proposal()
        self.source.priority = 2.0
        with self.assertRaisesRegex(ValueError, "stale"):
            GoalAlternativeAdapter.adopt(proposal, self.goals, self.lifecycle)
        self.assertEqual(len(self.goals.goals), 1)

    def test_replay_is_idempotent(self):
        proposal = self.proposal()
        first = GoalAlternativeAdapter.adopt(proposal, self.goals, self.lifecycle)
        second = GoalAlternativeAdapter.adopt(proposal, self.goals, self.lifecycle)
        self.assertEqual(first, second)
        self.assertEqual(len(self.lifecycle.snapshot()), 1)

    def test_combined_assessment_keeps_obsolescence_and_alternatives_separate(self):
        event = WorldEventLedger.make_event(
            "career-ended", 9, "career_path_closed",
            participants=("npc",), attributes={"reason": "permanent"},
        )
        assessment = GoalIntentionEvaluator.assess(
            self.goals, "career-goal", 10, events=(event,),
            review_policies=(GoalReviewPolicy(
                "career-obsolete", "career_path_closed", "career",
                GoalReviewAction.ABANDON,
                required_attributes=(("reason", "permanent"),),
            ),), emergence_rules=self.rules,
            need_deficits={"belonging": 0.9},
        )
        self.assertEqual(len(assessment.review_proposals), 1)
        self.assertEqual(assessment.review_proposals[0].action, GoalReviewAction.ABANDON)
        self.assertEqual(len(assessment.alternatives), 1)
        self.assertEqual(self.source.status, GoalStatus.ACTIVE)
    def test_same_category_emergence_is_not_labelled_an_alternative(self):
        same_category = (GoalEmergenceRule("another-career", GoalTemplate("promotion", "career", 3.0),
                          need_key="belonging", need_threshold=0.6),)
        self.assertEqual(GoalAlternativeEvaluator.assess(
            self.goals, "career-goal", 10, rules=same_category,
            need_deficits={"belonging": 0.9}), ())

if __name__ == "__main__":
    unittest.main()
