import unittest

from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.identity_decisions import IdentityChangeDecision
from simreality.identity_goal_alignment import (
    IdentityGoalAction, IdentityGoalAlignmentAdapter, IdentityGoalAlignmentPolicy,
    IdentityGoalReviewDecision, IdentityGoalReviewDecisionLedger,
    IdentityGoalReviewSnapshot,
)


class IdentityGoalAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal(
            "career-1", "npc-1", "career", 5.0, confidence=0.6,
            metadata={"identity_axis": "ambition"},
        ))
        self.goals.add(NPCGoal("family-1", "npc-2", "career", 4.0))
        self.policy = IdentityGoalAlignmentPolicy(
            "ambition-career", "ambition", "career",
            IdentityGoalAction.REPRIORITIZE, minimum_abs_delta=0.1,
            priority_delta=2.0, confidence_delta=0.1,
        )
        self.adapter = IdentityGoalAlignmentAdapter(self.goals, (self.policy,))
        self.accepted = IdentityChangeDecision(
            "identity-1", "event-1", "npc-1", "scar-policy", "ambition",
            True, 4, "I see myself differently", 0.0, 0.3, 0.3, 0.8, "participant",
        )
        self.rejected = IdentityChangeDecision(
            "identity-2", "event-2", "npc-1", "scar-policy", "ambition",
            False, 5, "That is not who I am", 0.3, 0.0, -0.3, 0.8, "participant",
        )

    def test_only_accepted_identity_decisions_generate_goal_proposals(self):
        before = self.goals.snapshot()
        self.assertEqual(self.adapter.assess((self.rejected,), current_tick=5), ())
        proposals = self.adapter.assess((self.accepted, self.rejected), current_tick=5)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].identity_decision_id, "identity-1")
        self.assertEqual(self.goals.snapshot(), before)

    def test_goal_change_requires_separate_acceptance_and_applies_once(self):
        proposal, = self.adapter.assess((self.accepted,), current_tick=5)
        ledger = IdentityGoalReviewDecisionLedger()
        decision = IdentityGoalReviewDecision(
            "goal-decision-1", proposal, True, 6, "My priorities have changed",
        )
        ledger.record(decision)
        self.assertEqual(self.goals.goals["career-1"].priority, 5.0)
        self.assertTrue(ledger.apply_accepted("goal-decision-1", self.goals))
        self.assertEqual(self.goals.goals["career-1"].priority, 7.0)
        self.assertFalse(ledger.apply_accepted("goal-decision-1", self.goals))
        self.assertEqual(self.goals.goals["career-1"].priority, 7.0)

    def test_rejection_is_durable_but_cannot_be_applied(self):
        proposal, = self.adapter.assess((self.accepted,), current_tick=5)
        ledger = IdentityGoalReviewDecisionLedger((
            IdentityGoalReviewDecision("goal-decision-2", proposal, False, 6, "Keep the goal"),
        ))
        with self.assertRaisesRegex(ValueError, "rejected"):
            ledger.apply_accepted("goal-decision-2", self.goals)
        self.assertEqual(self.goals.goals["career-1"].priority, 5.0)

    def test_snapshot_round_trip_preserves_decisions_and_applied_marker(self):
        proposal, = self.adapter.assess((self.accepted,), current_tick=5)
        ledger = IdentityGoalReviewDecisionLedger((
            IdentityGoalReviewDecision("goal-decision-3", proposal, True, 6, "Accepted"),
        ))
        ledger.apply_accepted("goal-decision-3", self.goals)
        snapshot = IdentityGoalReviewSnapshot.capture(ledger)
        restored = IdentityGoalReviewSnapshot.from_json(snapshot.to_json()).restore()
        self.assertEqual(restored.entries(), ledger.entries())
        self.assertTrue(restored.is_applied("goal-decision-3"))

    def test_stale_goal_state_is_not_overwritten(self):
        proposal, = self.adapter.assess((self.accepted,), current_tick=5)
        ledger = IdentityGoalReviewDecisionLedger((
            IdentityGoalReviewDecision("goal-decision-4", proposal, True, 6, "Accepted"),
        ))
        self.goals.goals["career-1"].priority = 8.0
        with self.assertRaisesRegex(ValueError, "stale"):
            ledger.apply_accepted("goal-decision-4", self.goals)



    def test_completed_goal_is_stale_and_cannot_be_reprioritized(self):
        proposal, = self.adapter.assess((self.accepted,), current_tick=5)
        ledger = IdentityGoalReviewDecisionLedger((
            IdentityGoalReviewDecision("goal-decision-5", proposal, True, 6, "Accepted"),
        ))
        self.goals.set_status("career-1", GoalStatus.COMPLETED)
        with self.assertRaisesRegex(ValueError, "stale"):
            ledger.apply_accepted("goal-decision-5", self.goals)

if __name__ == "__main__":
    unittest.main()
