"""Tests for NPC goal-review decisions and canonical persistence."""
import unittest

from simreality.goal_review import (
    GoalReviewAction, GoalReviewEvaluator, GoalReviewPolicy,
)
from simreality.goal_review_decisions import (
    GoalReviewDecision, GoalReviewDecisionLedger,
)
from simreality.goal_review_decisions_save_state import GoalReviewDecisionSnapshot
from simreality.goals import GoalBook, NPCGoal
from simreality.world_events import WorldEventLedger


class GoalReviewDecisionTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("career", "npc-1", "career", 5.0, confidence=0.7))
        event = WorldEventLedger.make_event(
            "promotion-denied", 4, "promotion_denied",
            participants=("npc-1",), attributes={"department": "engineering"},
        )
        evaluator = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy(
                "career-review", "promotion_denied", "career",
                GoalReviewAction.REPRIORITIZE, priority_delta=-2.0,
                confidence_delta=-0.1,
            ),
        ))
        self.proposal = evaluator.assess((event,))[0]

    def decision(self, decision_id="decision-1", accepted=True, tick=5, rationale="NPC reconsidered"):
        return GoalReviewDecision.from_proposal(
            decision_id, self.proposal, accepted=accepted,
            decision_tick=tick, rationale=rationale,
        )

    def test_acceptance_and_rejection_are_both_recorded(self):
        ledger = GoalReviewDecisionLedger()
        accepted = ledger.record(self.decision())
        self.assertTrue(accepted.accepted)
        self.assertEqual(ledger.get("decision-1"), accepted)

        rejected_proposal_event = WorldEventLedger.make_event(
            "second-event", 6, "promotion_denied", participants=("npc-1",),
        )
        second_proposal = GoalReviewEvaluator(self.goals, (
            GoalReviewPolicy("career-review", "promotion_denied", "career",
                             GoalReviewAction.PAUSE),
        )).assess((rejected_proposal_event,))[0]
        rejected = GoalReviewDecision.from_proposal(
            "decision-2", second_proposal, accepted=False,
            decision_tick=7, rationale="NPC prefers to continue",
        )
        ledger.record(rejected)
        self.assertFalse(ledger.get("decision-2").accepted)
        self.assertEqual(len(ledger.entries()), 2)

    def test_identical_replay_is_idempotent_but_conflicting_id_is_rejected(self):
        ledger = GoalReviewDecisionLedger()
        item = self.decision()
        self.assertEqual(ledger.record(item), item)
        self.assertEqual(ledger.record(item), item)
        with self.assertRaisesRegex(ValueError, "reused"):
            ledger.record(self.decision(accepted=False))

    def test_one_decision_per_review_proposal(self):
        ledger = GoalReviewDecisionLedger()
        ledger.record(self.decision())
        with self.assertRaisesRegex(ValueError, "already has"):
            ledger.record(self.decision("decision-2"))

    def test_batch_is_atomic_on_conflict(self):
        ledger = GoalReviewDecisionLedger()
        first = self.decision()
        second = self.decision("decision-2", accepted=False)
        with self.assertRaises(ValueError):
            ledger.record_many((first, second))
        self.assertEqual(ledger.entries(), ())

    def test_decision_tick_cannot_be_negative(self):
        with self.assertRaises(ValueError):
            self.decision(tick=-1)

    def test_snapshot_round_trip_and_stable_order(self):
        ledger = GoalReviewDecisionLedger((
            self.decision("z-decision", tick=8),
            self.decision("a-decision", tick=6, accepted=False),
        ))
        snapshot = GoalReviewDecisionSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = GoalReviewDecisionSnapshot.from_json(payload).restore()
        self.assertEqual(GoalReviewDecisionSnapshot.capture(restored), snapshot)
        self.assertEqual(
            [item.decision_id for item in restored.entries()],
            ["a-decision", "z-decision"],
        )

    def test_noncanonical_or_corrupt_snapshot_is_rejected(self):
        snapshot = GoalReviewDecisionSnapshot.capture(
            GoalReviewDecisionLedger((self.decision(),))
        )
        with self.assertRaises(ValueError):
            GoalReviewDecisionSnapshot.from_json(snapshot.to_json() + " ")
        with self.assertRaises(ValueError):
            GoalReviewDecisionSnapshot.from_json('{"schema_version":99,"records":[]}')

    def test_snapshot_rejects_duplicate_ids(self):
        record = GoalReviewDecisionSnapshot.capture(
            GoalReviewDecisionLedger((self.decision(),))
        ).records[0]
        with self.assertRaises(ValueError):
            GoalReviewDecisionSnapshot((record, record))


if __name__ == "__main__":
    unittest.main()
