import unittest
from simreality.action_evaluation import NPCPlanEvaluation
from simreality.npc_strategy_beliefs import (
    NPCStrategyBeliefLedger, StrategyBeliefSnapshot, StrategyLearningRule,
    StrategyObservation,
)

def evaluation(plan, status, confidence=1.0, missing=()):
    return NPCPlanEvaluation(plan, "npc-a", "find-food", ("search", "gather"),
        status, ("food",), () if missing else ("food",), tuple(missing),
        ("search", "gather") if status == "completed" else ("search",),
        () if status == "completed" else ("gather",),
        (), ("event-" + plan,), confidence)

class NPCStrategyBeliefTests(unittest.TestCase):
    def setUp(self):
        self.ledger = NPCStrategyBeliefLedger()
        self.rule = StrategyLearningRule("reliability-v1", minimum_observations=3,
                                         minimum_confidence_delta=0.12)

    def add(self, plan, status, tick, context="forest", confidence=1.0, missing=()):
        return self.ledger.observe_evaluation(
            evaluation(plan, status, confidence, missing), context, observed_tick=tick)

    def test_repeated_comparable_outcomes_propose_owner_specific_belief(self):
        first = self.add("p1", "failed", 1)
        self.add("p2", "failed", 2)
        self.add("p3", "completed", 3)
        proposal = self.ledger.assess("npc-a", first.strategy_id, "forest", self.rule)
        self.assertIsNotNone(proposal)
        self.assertLess(proposal.posterior_confidence, 0.5)
        self.assertEqual(proposal.sample_count, 3)
        self.assertEqual(len(proposal.observation_ids), 3)

    def test_single_failure_does_not_create_belief_or_proposal(self):
        observation = self.add("p1", "failed", 1)
        self.assertIsNone(self.ledger.assess("npc-a", observation.strategy_id, "forest", self.rule))
        self.assertIsNone(self.ledger.belief_for("npc-a", observation.strategy_id, "forest"))

    def test_contexts_and_npc_owners_are_isolated(self):
        obs = self.add("p1", "failed", 1, context="forest")
        self.add("p2", "failed", 2, context="forest")
        self.add("p3", "failed", 3, context="forest")
        self.assertIsNone(self.ledger.assess("npc-a", obs.strategy_id, "city", self.rule))
        other = evaluation("other", "failed")
        other = NPCPlanEvaluation(other.plan_id, "npc-b", other.goal_id, other.planned_actions,
            other.terminal_status, other.expected_goal_facts, other.observed_goal_facts,
            other.missing_goal_facts, other.completed_actions, other.failed_actions,
            other.deviation_flags, other.evidence_event_ids, other.confidence)
        self.ledger.observe_evaluation(other, "forest", observed_tick=4)
        self.assertIsNone(self.ledger.assess("npc-b", obs.strategy_id, "forest", self.rule))

    def test_replanned_execution_is_neutral(self):
        self.assertIsNone(self.add("p1", "replanned", 1))
        self.assertEqual(self.ledger.observations(), ())

    def test_decisions_require_explicit_acceptance_and_rejection_is_historical(self):
        obs = [self.add("p1", "failed", 1), self.add("p2", "failed", 2), self.add("p3", "failed", 3)]
        proposal = self.ledger.assess("npc-a", obs[0].strategy_id, "forest", self.rule)
        rejected = self.ledger.decide(proposal, accepted=False, decision_tick=4,
                                      rationale="Evidence is too narrow")
        self.assertIsNone(self.ledger.belief_for("npc-a", obs[0].strategy_id, "forest"))
        self.assertEqual(self.ledger.decisions(), (rejected,))
        with self.assertRaisesRegex(ValueError, "already has a decision"):
            self.ledger.decide(proposal, accepted=True, decision_tick=4, rationale="Changed my mind")

    def test_accepted_belief_can_be_revised_by_later_accepted_evidence(self):
        obs = [self.add("p1", "failed", 1), self.add("p2", "failed", 2), self.add("p3", "failed", 3)]
        proposal = self.ledger.assess("npc-a", obs[0].strategy_id, "forest", self.rule)
        first = self.ledger.decide(proposal, accepted=True, decision_tick=4, rationale="Repeated failures")
        belief = self.ledger.belief_for("npc-a", obs[0].strategy_id, "forest")
        self.assertEqual(belief.decision_id, first.decision_id)
        self.add("p4", "completed", 5)
        second_proposal = self.ledger.assess("npc-a", obs[0].strategy_id, "forest", self.rule)
        second = self.ledger.decide(second_proposal, accepted=True, decision_tick=6, rationale="New evidence changes my view")
        self.assertGreater(self.ledger.belief_for("npc-a", obs[0].strategy_id, "forest").confidence, belief.confidence)
        self.assertNotEqual(first.decision_id, second.decision_id)

    def test_strategy_identity_includes_goal_and_ordered_action_sequence(self):
        first = self.add("p1", "failed", 1)
        alternate = NPCPlanEvaluation("p2", "npc-a", "find-food", ("gather", "search"),
            "failed", ("food",), (), ("food",), (), ("gather",), (), ("event-p2",), 1.0)
        second = self.ledger.observe_evaluation(alternate, "forest", observed_tick=2)
        self.assertNotEqual(first.strategy_id, second.strategy_id)

    def test_accepted_beliefs_export_planner_reliability(self):
        observations = [self.add("p1", "failed", 1), self.add("p2", "failed", 2), self.add("p3", "failed", 3)]
        proposal = self.ledger.assess("npc-a", observations[0].strategy_id, "forest", self.rule)
        self.ledger.decide(proposal, accepted=True, decision_tick=4, rationale="Repeated failures")
        self.assertEqual(self.ledger.plan_reliabilities("npc-a", "forest"),
                         {("find-food", ("search", "gather")): proposal.posterior_confidence})

    def test_zero_confidence_evaluation_is_not_a_learning_sample(self):
        self.assertIsNone(self.add("p1", "failed", 1, confidence=0.0))
        self.assertEqual(self.ledger.observations(), ())

    def test_snapshot_round_trip_preserves_observations_and_decisions(self):
        obs = [self.add("p1", "failed", 1), self.add("p2", "failed", 2), self.add("p3", "failed", 3)]
        proposal = self.ledger.assess("npc-a", obs[0].strategy_id, "forest", self.rule)
        self.ledger.decide(proposal, accepted=True, decision_tick=4, rationale="Repeated failure")
        encoded = StrategyBeliefSnapshot.capture(self.ledger).to_json()
        restored = StrategyBeliefSnapshot.from_json(encoded).restore()
        self.assertEqual(restored.observations(), self.ledger.observations())
        self.assertEqual(restored.decisions(), self.ledger.decisions())
        self.assertEqual(StrategyBeliefSnapshot.capture(restored).to_json(), encoded)

    def test_observation_id_reuse_with_conflicting_content_is_rejected(self):
        item = self.add("p1", "failed", 1)
        altered = StrategyObservation(
            item.observation_id, item.owner_id, item.goal_id, item.strategy_id,
            item.context_key, "different-plan", item.action_sequence, item.outcome, item.confidence,
            item.observed_tick, item.evidence_event_ids, item.reflection_id)
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.ledger.record(altered)

if __name__ == "__main__":
    unittest.main()
