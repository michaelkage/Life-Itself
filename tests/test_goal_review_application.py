"""Explicit application of accepted NPC goal-review decisions."""
import unittest

from simreality.goal_review import GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy
from simreality.goal_review_application import (
    GoalReviewApplicationAdapter, GoalReviewApplicationLedger,
)
from simreality.goal_review_application_save_state import GoalReviewApplicationSnapshot
from simreality.goal_review_decisions import GoalReviewDecision
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.npc_goal_emergence import GoalLifecycleLedger
from simreality.world_events import WorldEventLedger


class GoalReviewApplicationTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("career", "npc-1", "career", 5.0, confidence=0.7))
        self.event = WorldEventLedger.make_event(
            "setback", 4, "promotion_denied", participants=("npc-1",),
        )

    def decision(self, action=GoalReviewAction.REPRIORITIZE, accepted=True,
                 priority_delta=-2.0, target_category=None, tick=5):
        policy = GoalReviewPolicy(
            "review", "promotion_denied", "career", action,
            priority_delta=priority_delta, confidence_delta=-0.1,
            target_category=target_category,
        )
        proposal = GoalReviewEvaluator(self.goals, (policy,)).assess((self.event,))[0]
        return GoalReviewDecision.from_proposal(
            "decision-1", proposal, accepted=accepted, decision_tick=tick,
            rationale="NPC explicitly reconsidered the setback",
        )

    def test_accepted_reprioritization_applies_once(self):
        decision = self.decision()
        ledger = GoalReviewApplicationLedger()
        result = GoalReviewApplicationAdapter.apply(decision, self.goals, ledger)
        self.assertEqual(self.goals.goals["career"].priority, 3.0)
        self.assertEqual(self.goals.goals["career"].confidence, 0.6)
        self.assertEqual(self.goals.goals["career"].review_tick, 5)
        self.assertEqual(GoalReviewApplicationAdapter.apply(
            decision, self.goals, ledger), result)
        self.assertEqual(len(ledger.entries()), 1)

    def test_rejected_decision_is_never_applied(self):
        with self.assertRaisesRegex(ValueError, "rejected"):
            GoalReviewApplicationAdapter.apply(
                self.decision(accepted=False), self.goals,
                GoalReviewApplicationLedger(),
            )
        self.assertEqual(self.goals.goals["career"].priority, 5.0)

    def test_stale_goal_values_are_rejected_without_mutation(self):
        decision = self.decision()
        self.goals.goals["career"].priority = 4.0
        with self.assertRaisesRegex(ValueError, "stale"):
            GoalReviewApplicationAdapter.apply(
                decision, self.goals, GoalReviewApplicationLedger(),
            )
        self.assertEqual(self.goals.goals["career"].confidence, 0.7)

    def test_reframe_updates_category_and_reviewed_values(self):
        result = GoalReviewApplicationAdapter.apply(
            self.decision(GoalReviewAction.REFRAME, target_category="entrepreneurship"),
            self.goals, GoalReviewApplicationLedger(),
        )
        self.assertEqual(result.resulting_category, "entrepreneurship")
        self.assertEqual(self.goals.goals["career"].category, "entrepreneurship")

    def test_abandon_requires_and_records_lifecycle(self):
        decision = self.decision(GoalReviewAction.ABANDON)
        with self.assertRaisesRegex(ValueError, "require"):
            GoalReviewApplicationAdapter.apply(
                decision, self.goals, GoalReviewApplicationLedger(),
            )
        lifecycle = GoalLifecycleLedger()
        applications = GoalReviewApplicationLedger()
        result = GoalReviewApplicationAdapter.apply(
            decision, self.goals, applications, lifecycle=lifecycle,
        )
        self.assertEqual(result.resulting_status, GoalStatus.ABANDONED)
        self.assertEqual(self.goals.goals["career"].status, GoalStatus.ABANDONED)
        self.assertEqual(lifecycle.snapshot()[-1].evidence_ids, (self.event.event_id,))

    def test_pause_is_explicitly_recorded_without_inventing_paused_status(self):
        result = GoalReviewApplicationAdapter.apply(
            self.decision(GoalReviewAction.PAUSE), self.goals,
            GoalReviewApplicationLedger(),
        )
        self.assertEqual(result.resulting_status, GoalStatus.ACTIVE)
        self.assertEqual(self.goals.goals["career"].status, GoalStatus.ACTIVE)
        self.assertEqual(self.goals.goals["career"].review_tick, 5)

    def test_application_snapshot_round_trip(self):
        applications = GoalReviewApplicationLedger()
        GoalReviewApplicationAdapter.apply(
            self.decision(), self.goals, applications,
        )
        snapshot = GoalReviewApplicationSnapshot.capture(applications)
        restored = GoalReviewApplicationSnapshot.from_json(snapshot.to_json()).restore()
        self.assertEqual(GoalReviewApplicationSnapshot.capture(restored), snapshot)


if __name__ == "__main__":
    unittest.main()
