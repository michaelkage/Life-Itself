from __future__ import annotations

import unittest

from simreality.goal_intention_memory import GoalIntentionMemoryLedger
from simreality.goal_intention_recall import (
    GoalIntentionRecallAdapter, GoalIntentionRecallRule,
)
from simreality.goal_intention_continuity import GoalIntentionContinuityAdapter
from simreality.goal_arbitration import GoalCommitmentLedger
from simreality.goals import GoalBook, NPCGoal


class GoalIntentionRecallTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("g1", "alice", "survival", 0.8))
        self.goals.add(NPCGoal("g2", "alice", "family", 0.72))
        self.goals.add(NPCGoal("foreign", "bob", "survival", 10.0))

    def test_recall_is_authored_decayed_and_provenance_linked(self):
        ledger = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation",
                "plan-1", "A plan failed", ("event-1",),
            ),
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 5, "personal_experience", "autobiographical_memory",
                "memory-1", "I remember the cold", ("event-2", "memory-1"),
            ),
            GoalIntentionMemoryLedger.make(
                "bob", "foreign", 0, "plan_failed", "plan_evaluation",
                "plan-b", "Other person's experience", ("event-b",),
            ),
        ))
        result = GoalIntentionRecallAdapter.recall(
            ledger, self.goals, "alice", 10,
            rules=(GoalIntentionRecallRule(
                "g1", (("plan_failed", -0.2), ("personal_experience", 0.1)),
                half_life_ticks=10.0,
            ),),
        )
        # Five half-lives? The first memory is ten ticks old, the second five.
        self.assertAlmostEqual(dict(result.adjustments)["g1"], -0.1 + 0.1 * (2 ** -0.5))
        self.assertEqual(len(result.evidence), 2)
        self.assertEqual({item.memory_id for item in result.evidence},
                         {item.memory_id for item in ledger.entries("alice")})
        self.assertEqual(result.owner_id, "alice")
        self.assertEqual(result.tick, 10)

    def test_unweighted_memories_do_not_affect_goal_arbitration(self):
        ledger = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation",
                "plan-1", "Failure narrative has no automatic meaning",
            ),
        ))
        result = GoalIntentionRecallAdapter.recall(
            ledger, self.goals, "alice", 1, rules=(),
        )
        self.assertEqual(result.adjustments, ())
        self.assertEqual(result.evidence, ())

    def test_multiple_memories_are_bounded_by_authored_goal_limit(self):
        entries = tuple(
            GoalIntentionMemoryLedger.make(
                "alice", "g1", tick, "plan_failed", "plan_evaluation",
                f"plan-{tick}", f"Failure {tick}",
            )
            for tick in range(8)
        )
        result = GoalIntentionRecallAdapter.recall(
            GoalIntentionMemoryLedger(entries), self.goals, "alice", 8,
            rules=(GoalIntentionRecallRule(
                "g1", (("plan_failed", -0.25),), half_life_ticks=1.0,
                max_adjustment=0.2,
            ),),
        )
        self.assertEqual(dict(result.adjustments)["g1"], -0.2)
        self.assertEqual(len(result.evidence), 8)

    def test_recall_rejects_foreign_goal_rules_and_future_memories(self):
        with self.assertRaisesRegex(ValueError, "owned by the NPC"):
            GoalIntentionRecallAdapter.recall(
                GoalIntentionMemoryLedger(), self.goals, "alice", 1,
                rules=(GoalIntentionRecallRule("foreign", (("failed", -0.1),)),),
            )
        future = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 3, "plan_failed", "plan_evaluation", "plan-future", "Future",
            ),
        ))
        with self.assertRaisesRegex(ValueError, "future"):
            GoalIntentionRecallAdapter.recall(
                future, self.goals, "alice", 2,
                rules=(GoalIntentionRecallRule("g1", (("plan_failed", -0.1),)),),
            )

    def test_recall_identity_changes_when_evidence_changes(self):
        first = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation", "plan-1", "Failure",
            ),
        ))
        second = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation", "plan-1", "Failure",
            ),
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 1, "plan_failed", "plan_evaluation", "plan-2", "Failure again",
            ),
        ))
        rule = (GoalIntentionRecallRule("g1", (("plan_failed", -0.1),)),)
        a = GoalIntentionRecallAdapter.recall(first, self.goals, "alice", 2, rules=rule)
        b = GoalIntentionRecallAdapter.recall(second, self.goals, "alice", 2, rules=rule)
        self.assertNotEqual(a.recall_id, b.recall_id)


    def test_recall_identity_binds_memory_content_and_source_provenance(self):
        first_memory = GoalIntentionMemoryLedger.make(
            "alice", "g1", 0, "plan_failed", "plan_evaluation",
            "plan-1", "The bridge was unsafe", ("event-1",),
        )
        changed_memory = GoalIntentionMemoryLedger.make(
            "alice", "g1", 0, "plan_failed", "plan_evaluation",
            "plan-1", "The bridge was safe", ("event-2",),
        )
        rule = (GoalIntentionRecallRule("g1", (("plan_failed", -0.1),)),)
        first = GoalIntentionRecallAdapter.recall(
            GoalIntentionMemoryLedger((first_memory,)), self.goals, "alice", 1, rules=rule,
        )
        changed = GoalIntentionRecallAdapter.recall(
            GoalIntentionMemoryLedger((changed_memory,)), self.goals, "alice", 1, rules=rule,
        )
        self.assertEqual(first.evidence[0].memory_id, changed.evidence[0].memory_id)
        self.assertNotEqual(first.evidence[0].content_digest, changed.evidence[0].content_digest)
        self.assertNotEqual(first.recall_id, changed.recall_id)


    def test_reflection_influences_fresh_arbitration_without_locking_the_goal(self):
        commitments = GoalCommitmentLedger()
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, commitments, "alice", 0, rationale="initial focus",
            continuity_margin=0.0,
        )
        self.assertEqual(first.commitment.selected_goal_id, "g1")
        memories = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation",
                "plan-1", "The previous approach failed", ("event-1",),
            ),
        ))
        second = GoalIntentionContinuityAdapter.reconsider(
            self.goals, commitments, "alice", 1, rationale="reconsider after experience",
            continuity_margin=0.0,
            intention_memories=memories,
            recall_rules=(GoalIntentionRecallRule(
                "g1", (("plan_failed", -0.25),), half_life_ticks=1.0,
            ),),
        )
        self.assertEqual(second.commitment.selected_goal_id, "g2")
        self.assertIsNotNone(second.intention_recall)
        self.assertEqual(second.intention_recall.evidence[0].memory_id, memories.entries()[0].memory_id)
        self.assertEqual(self.goals.goals["g1"].status.value, "active")

    def test_recall_rules_require_memory_ledger(self):
        with self.assertRaisesRegex(ValueError, "intention_memories are required"):
            GoalIntentionContinuityAdapter.reconsider(
                self.goals, GoalCommitmentLedger(), "alice", 0,
                rationale="focus",
                recall_rules=(GoalIntentionRecallRule("g1", (("plan_failed", -0.1),)),),
            )


    def test_changed_recall_evidence_cannot_fork_same_tick_commitment(self):
        commitments = GoalCommitmentLedger()
        memories = GoalIntentionMemoryLedger((
            GoalIntentionMemoryLedger.make(
                "alice", "g1", 0, "plan_failed", "plan_evaluation",
                "plan-1", "First failure",
            ),
        ))
        rules = (GoalIntentionRecallRule(
            "g1", (("plan_failed", -0.1),), half_life_ticks=10.0,
        ),)
        first = GoalIntentionContinuityAdapter.reconsider(
            self.goals, commitments, "alice", 1, rationale="reflect",
            intention_memories=memories, recall_rules=rules,
        )
        memories.record(GoalIntentionMemoryLedger.make(
            "alice", "g1", 1, "plan_failed", "plan_evaluation",
            "plan-2", "Second failure",
        ))
        with self.assertRaisesRegex(ValueError, "already exists"):
            GoalIntentionContinuityAdapter.reconsider(
                self.goals, commitments, "alice", 1, rationale="reflect again",
                intention_memories=memories, recall_rules=rules,
            )


if __name__ == "__main__":
    unittest.main()
