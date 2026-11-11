"""Need and circumstance recovery proposals for abandoned NPC intentions."""
import unittest

from simreality.goal_recovery import (
    GoalRecoveryAdapter, GoalRecoveryEvaluator, GoalRecoveryRule,
)
from simreality.goals import GoalBook, GoalStatus, NPCGoal
from simreality.npc_goal_emergence import GoalLifecycleLedger


class GoalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.goals = GoalBook()
        self.goals.add(NPCGoal("housing", "npc-1", "housing", 4.0, confidence=0.6))
        self.lifecycle = GoalLifecycleLedger()
        self.lifecycle.transition(
            self.goals, "housing", GoalStatus.ABANDONED, 1,
            "The NPC could not afford stable housing",
        )
        self.rule = GoalRecoveryRule(
            "housing-recovery", "housing", need_key="financial_pressure",
            maximum_need_level=0.35, required_facts=("shelter_available",),
        )
        self.needs = {"financial_pressure": 0.2}
        self.facts = frozenset({"shelter_available"})

    def assess(self, tick=2):
        return GoalRecoveryEvaluator.assess(
            self.goals, "npc-1", tick, rules=(self.rule,),
            need_levels=self.needs, available_facts=self.facts,
        )

    def test_recovered_need_and_circumstance_propose_reopening(self):
        proposals = self.assess()
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        event = GoalRecoveryAdapter.apply(
            proposal, self.goals, self.lifecycle,
            need_levels=self.needs, available_facts=self.facts,
        )
        self.assertEqual(event.from_status, "abandoned")
        self.assertEqual(event.to_status, "active")
        self.assertEqual(self.goals.goals["housing"].status, GoalStatus.ACTIVE)

    def test_unrecovered_need_or_missing_fact_suppresses_proposal(self):
        self.needs = {"financial_pressure": 0.8}
        self.assertEqual(self.assess(), ())
        self.needs = {"financial_pressure": 0.2}
        self.facts = frozenset()
        self.assertEqual(self.assess(), ())

    def test_changed_circumstances_make_proposal_stale(self):
        proposal = self.assess()[0]
        changed_needs = {"financial_pressure": 0.9}
        with self.assertRaisesRegex(ValueError, "circumstances changed"):
            GoalRecoveryAdapter.apply(
                proposal, self.goals, self.lifecycle,
                need_levels=changed_needs, available_facts=self.facts,
            )
        self.assertEqual(self.goals.goals["housing"].status, GoalStatus.ABANDONED)

    def test_goal_mutation_makes_proposal_stale(self):
        proposal = self.assess()[0]
        self.goals.goals["housing"].priority = 5.0
        with self.assertRaisesRegex(ValueError, "goal recovery proposal is stale"):
            GoalRecoveryAdapter.apply(
                proposal, self.goals, self.lifecycle,
                need_levels=self.needs, available_facts=self.facts,
            )

    def test_active_goals_are_not_recovery_candidates(self):
        self.lifecycle.transition(
            self.goals, "housing", GoalStatus.ACTIVE, 2,
            "Circumstances improved",
        )
        self.assertEqual(self.assess(tick=3), ())


if __name__ == "__main__":
    unittest.main()
