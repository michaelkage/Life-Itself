from __future__ import annotations

import unittest

from simreality.goal_arbitration import (
    GoalArbitrationEvaluator, GoalArbitrationRule, GoalCommitmentAdapter,
    GoalCommitmentLedger,
)
from simreality.goal_arbitration_save_state import GoalCommitmentSnapshot
from simreality.goals import GoalBook, NPCGoal, GoalStatus
from simreality.identity_context import NPCEmotionalState


class GoalArbitrationTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("rent", "npc-1", "security", 8, deadline_tick=12))
        self.goals.add(NPCGoal("art", "npc-1", "creative", 7))
        self.goals.add(NPCGoal("visit", "npc-1", "social", 6))
        self.goals.add(NPCGoal("other", "npc-2", "security", 99))

    def test_need_emotion_and_value_alignment_can_change_winner(self):
        before = self.goals.snapshot()
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5,
            rules=(
                GoalArbitrationRule("art", need_axis="creative", need_weight=1,
                                    emotion_axis="joy", emotion_weight=1,
                                    value_axis="craft", value_weight=1),
                GoalArbitrationRule("rent", importance=0.4),
            ),
            need_deficits={"creative": 1},
            emotional_state=NPCEmotionalState("npc-1", 5, {"joy": 1}),
            value_alignment={"craft": 1},
            resources={"money": 100},
        )
        self.assertEqual(assessment.selected_goal_id, "art")
        self.assertEqual(self.goals.snapshot(), before)
        self.assertEqual(assessment.deferred_goal_ids, ("rent", "visit"))

    def test_resource_infeasibility_defers_goal_and_selects_feasible_fallback(self):
        rules = (
            GoalArbitrationRule("rent", resource_costs=(("money", 500),)),
            GoalArbitrationRule("art", resource_costs=(("wood", 2),)),
        )
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5, rules=rules, resources={"money": 10, "wood": 3}
        )
        self.assertEqual(assessment.selected_goal_id, "art")
        rent = next(x for x in assessment.candidates if x.goal_id == "rent")
        self.assertFalse(rent.feasible)
        self.assertIn("needs 500 money", rent.feasibility_reason)

    def test_commitment_defers_without_abandoning_other_goals(self):
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5, resources={}
        )
        before = self.goals.snapshot()
        ledger = GoalCommitmentLedger()
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, ledger, rationale="urgent personal obligation"
        )
        self.assertEqual(commitment.selected_goal_id, "rent")
        self.assertEqual(commitment.deferred_goal_ids, ("art", "visit"))
        self.assertEqual(self.goals.snapshot(), before)
        self.assertEqual(self.goals.goals["art"].status, GoalStatus.ACTIVE)

    def test_commitment_is_idempotent_and_one_per_owner_tick(self):
        assessment = GoalArbitrationEvaluator.assess(self.goals, "npc-1", 5)
        ledger = GoalCommitmentLedger()
        first = GoalCommitmentAdapter.commit(assessment, self.goals, ledger, rationale="focus")
        second = GoalCommitmentAdapter.commit(assessment, self.goals, ledger, rationale="ignored on replay")
        self.assertEqual(first, second)
        competing = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5,
            rules=(GoalArbitrationRule("art", importance=1),)
        )
        with self.assertRaisesRegex(ValueError, "already has a commitment"):
            GoalCommitmentAdapter.commit(competing, self.goals, ledger, rationale="conflict")

    def test_stale_goal_state_rejects_commitment(self):
        assessment = GoalArbitrationEvaluator.assess(self.goals, "npc-1", 5)
        self.goals.goals["rent"].priority = 1
        with self.assertRaisesRegex(ValueError, "stale"):
            GoalCommitmentAdapter.commit(
                assessment, self.goals, GoalCommitmentLedger(), rationale="focus"
            )

    def test_commitment_snapshot_round_trip_and_canonical_validation(self):
        assessment = GoalArbitrationEvaluator.assess(self.goals, "npc-1", 5)
        ledger = GoalCommitmentLedger()
        GoalCommitmentAdapter.commit(assessment, self.goals, ledger, rationale="focus")
        snapshot = GoalCommitmentSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = GoalCommitmentSnapshot.from_json(payload).restore()
        self.assertEqual(restored.entries(), ledger.entries())
        with self.assertRaises(ValueError):
            GoalCommitmentSnapshot.from_json(payload + " ")


if __name__ == "__main__":
    unittest.main()
