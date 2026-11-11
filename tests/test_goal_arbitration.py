from __future__ import annotations

import unittest
from dataclasses import replace

from simreality.goal_arbitration import (
    GoalArbitrationEvaluator, GoalArbitrationRule, GoalCommitmentAdapter,
    GoalCommitmentLedger,
)
from simreality.goal_arbitration_save_state import GoalCommitmentSnapshot
from simreality.goal_intention_continuity import GoalIntentionContinuityAdapter
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
        self.assertEqual(ledger.latest_for_owner("npc-1"), first)
        self.assertEqual(ledger.at_tick("npc-1", 5), first)
        self.assertIsNone(ledger.at_tick("npc-1", 6))
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




    def test_commitment_identity_must_match_assessment_digest(self):
        assessment = GoalArbitrationEvaluator.assess(self.goals, "npc-1", 5)
        commitment = GoalCommitmentAdapter.commit(
            assessment, self.goals, GoalCommitmentLedger(), rationale="focus",
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            replace(commitment, commitment_id="0" * 64)

    def test_commitment_ledger_batch_restore_is_atomic_on_tick_conflict(self):
        first_assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5,
        )
        second_assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5,
            rules=(GoalArbitrationRule("art", importance=1.0),),
        )
        first = GoalCommitmentAdapter.commit(
            first_assessment, self.goals, GoalCommitmentLedger(), rationale="first focus",
        )
        second = GoalCommitmentAdapter.commit(
            second_assessment, self.goals, GoalCommitmentLedger(), rationale="competing focus",
        )
        restored = GoalCommitmentLedger((first,))
        self.assertEqual(restored.entries(), (first,))
        target = GoalCommitmentLedger()
        with self.assertRaisesRegex(ValueError, "already has a commitment"):
            target.record_many((first, second))
        self.assertEqual(target.entries(), ())

    def test_deferred_ambition_can_win_a_later_arbitration(self):
        first = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5, resources={}
        )
        ledger = GoalCommitmentLedger()
        committed = GoalCommitmentAdapter.commit(
            first, self.goals, ledger, rationale="meet urgent obligation"
        )
        self.assertEqual(committed.selected_goal_id, "rent")
        second = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 6,
            rules=(GoalArbitrationRule("art", importance=1.0),),
            resources={},
        )
        self.assertEqual(second.selected_goal_id, "art")
        self.assertEqual(self.goals.goals["rent"].status, GoalStatus.ACTIVE)
        self.assertEqual(self.goals.goals["art"].status, GoalStatus.ACTIVE)

    def test_no_feasible_goal_cannot_be_committed(self):
        assessment = GoalArbitrationEvaluator.assess(
            self.goals, "npc-1", 5,
            rules=(
                GoalArbitrationRule("rent", resource_costs=(("money", 100),)),
                GoalArbitrationRule("art", resource_costs=(("wood", 50),)),
                GoalArbitrationRule("visit", resource_costs=(("time", 100),)),
            ),
            resources={"money": 1, "wood": 1},
        )
        self.assertIsNone(assessment.selected_goal_id)
        with self.assertRaisesRegex(ValueError, "no resource-feasible"):
            GoalCommitmentAdapter.commit(
                assessment, self.goals, GoalCommitmentLedger(), rationale="cannot afford either"
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


    def test_continuity_retains_feasible_incumbent_through_small_score_change(self):
        ledger = GoalCommitmentLedger()
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 5, rationale="initial focus",
        )
        incumbent = first.commitment.selected_goal_id
        challenger = "art" if incumbent != "art" else "visit"
        second = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 6, rationale="continue current ambition",
            continuity_margin=1.0,
            rules=(GoalArbitrationRule(challenger, importance=0.1),),
        )
        self.assertEqual(second.commitment.selected_goal_id, incumbent)
        self.assertTrue(second.retained_previous_focus)
        self.assertEqual(second.previous_commitment, first.commitment)
        self.assertEqual(self.goals.goals[incumbent].status, GoalStatus.ACTIVE)

    def test_materially_stronger_challenger_replaces_incumbent(self):
        ledger = GoalCommitmentLedger()
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 5, rationale="initial focus",
            continuity_margin=0.0,
        )
        challenger = "art" if first.commitment.selected_goal_id != "art" else "visit"
        self.goals.goals[challenger].priority = 100.0
        second = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 6, rationale="new urgent need",
            continuity_margin=0.05,
            rules=(GoalArbitrationRule(challenger, importance=1.0),),
        )
        self.assertEqual(second.commitment.selected_goal_id, challenger)
        self.assertFalse(second.retained_previous_focus)
        self.assertEqual(self.goals.goals[first.commitment.selected_goal_id].status, GoalStatus.ACTIVE)

    def test_infeasible_incumbent_is_never_protected_by_continuity(self):
        ledger = GoalCommitmentLedger()
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 5, rationale="initial focus",
            continuity_margin=1.0,
        )
        incumbent = first.commitment.selected_goal_id
        second = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 6, rationale="resources changed",
            continuity_margin=1.0,
            rules=(GoalArbitrationRule(incumbent, resource_costs=(("money", 10),)),),
            resources={"money": 0},
        )
        self.assertNotEqual(second.commitment.selected_goal_id, incumbent)
        self.assertFalse(second.retained_previous_focus)

    def test_continuity_restores_from_snapshot_and_replays_same_tick(self):
        ledger = GoalCommitmentLedger()
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 5, rationale="initial focus",
        )
        restored = GoalCommitmentSnapshot.from_json(
            GoalCommitmentSnapshot.capture(ledger).to_json()
        ).restore()
        replay = GoalIntentionContinuityAdapter.reconsider(
            self.goals, restored, "npc-1", 5, rationale="ignored on replay",
        )
        self.assertEqual(replay.commitment, first.commitment)
        self.assertEqual(replay.assessment.assessment_id, first.assessment.assessment_id)
        next_tick = GoalIntentionContinuityAdapter.reconsider(
            self.goals, restored, "npc-1", 6, rationale="fresh next-tick assessment",
        )
        self.assertEqual(next_tick.previous_commitment, first.commitment)
        self.assertEqual(next_tick.commitment.tick, 6)
        replay_next_tick = GoalIntentionContinuityAdapter.reconsider(
            self.goals, restored, "npc-1", 6, rationale="replayed next tick",
        )
        self.assertEqual(replay_next_tick.commitment, next_tick.commitment)
        self.assertEqual(replay_next_tick.assessment.assessment_id,
                         next_tick.assessment.assessment_id)

    def test_same_tick_reassessment_cannot_fork_committed_decision(self):
        ledger = GoalCommitmentLedger()
        GoalIntentionContinuityAdapter.reconsider(
            self.goals, ledger, "npc-1", 5, rationale="initial focus",
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            GoalIntentionContinuityAdapter.reconsider(
                self.goals, ledger, "npc-1", 5, rationale="changed inputs",
                rules=(GoalArbitrationRule("art", importance=1.0),),
            )


if __name__ == "__main__":
    unittest.main()
