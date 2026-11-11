from __future__ import annotations
import unittest
from simreality.action_evaluation import NPCPlanEvaluation
from simreality.npc_goal_reflection import GoalReflectionAlternative, GoalReflectionRule, NPCGoalReflectiveReasoner
from simreality.planning import DeterministicPlanner, PlanningAction
from simreality.world_events import WorldEventLedger

class NPCGoalReflectiveReasonerTests(unittest.TestCase):
    def setUp(self):
        self.planner = DeterministicPlanner((
            PlanningAction("bridge", frozenset({"at_river"}), frozenset({"across"}), cost=1),
            PlanningAction("boat", frozenset({"at_river", "boat_available"}), frozenset({"across"}), cost=3),
            PlanningAction("walk", frozenset({"at_river", "road_open"}), frozenset({"across"}), cost=5),
        ))
        self.evaluation = NPCPlanEvaluation(
            "plan-1", "alice", "rescue", ("bridge",), "failed",
            ("across",), (), ("across",), (), ("bridge",),
            ("action_deviation:interrupted", "goal_not_achieved"), ("event-1",), 0.9)
        self.events = WorldEventLedger((WorldEventLedger.make_event(
            "event-1", 4, "bridge_destroyed", participants=("alice", "bob")),))

    def reflect(self, **kwargs):
        return NPCGoalReflectiveReasoner.reflect(
            self.evaluation, self.events, self.planner,
            {"at_river", "boat_available", "road_open"}, {"across"},
            current_tick=5, rule=kwargs.pop("rule", GoalReflectionRule()), **kwargs)

    def test_exact_evidence_attributes_changed_circumstances(self):
        result = self.reflect(rule=GoalReflectionRule(
            deviation_causes=(("action_deviation:interrupted", "own_decision", 0.2),),
            event_type_causes=(("bridge_destroyed", "changed_circumstances", 0.8),)))
        self.assertEqual(result.primary_cause, "changed_circumstances")
        self.assertEqual(dict(result.causes), {"changed_circumstances": 0.8, "own_decision": 0.2})

    def test_another_npc_requires_non_owner_participant(self):
        events = WorldEventLedger((WorldEventLedger.make_event(
            "event-1", 4, "interference", participants=("alice",)),))
        result = NPCGoalReflectiveReasoner.reflect(
            self.evaluation, events, self.planner, {"at_river"}, {"across"},
            current_tick=5, rule=GoalReflectionRule(
                event_type_causes=(("interference", "another_npc", 1.0),)))
        self.assertEqual(result.primary_cause, "undetermined")

    def test_resource_shortfall_is_explicit(self):
        result = self.reflect(resource_shortfalls=(("food", 10.0, 2.0),))
        self.assertAlmostEqual(dict(result.causes)["insufficient_resources"], 0.8)

    def test_counterfactuals_are_deterministic_and_comparable(self):
        alts = (GoalReflectionAlternative("avoid-bridge", ("bridge",)),
                GoalReflectionAlternative("avoid-boat", ("boat",)))
        first = self.reflect(alternatives=alts, rule=GoalReflectionRule(max_alternatives=2))
        second = self.reflect(alternatives=alts, rule=GoalReflectionRule(max_alternatives=2))
        self.assertEqual(first.reflection_id, second.reflection_id)
        self.assertEqual({x.alternative_id: x.plan.actions for x in first.counterfactuals},
                         {"avoid-bridge": ("boat",), "avoid-boat": ("bridge",)})
        self.assertEqual({x.alternative_id: x.cost_delta for x in first.counterfactuals},
                         {"avoid-bridge": 2, "avoid-boat": 0})

    def test_unknown_action_and_excess_alternatives_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown action"):
            self.reflect(alternatives=(GoalReflectionAlternative("bad", ("missing",)),))
        with self.assertRaisesRegex(ValueError, "authored rule limit"):
            self.reflect(alternatives=(GoalReflectionAlternative("one", ()),),
                         rule=GoalReflectionRule(max_alternatives=0))

    def test_missing_and_future_evidence_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing event"):
            NPCGoalReflectiveReasoner.reflect(
                self.evaluation, WorldEventLedger(), self.planner, {"at_river"}, {"across"},
                current_tick=5, rule=GoalReflectionRule())
        future = WorldEventLedger((WorldEventLedger.make_event(
            "event-1", 6, "storm", participants=("alice",)),))
        with self.assertRaisesRegex(ValueError, "future"):
            NPCGoalReflectiveReasoner.reflect(
                self.evaluation, future, self.planner, {"at_river"}, {"across"},
                current_tick=5, rule=GoalReflectionRule())

    def test_invalid_resource_shortfall_cannot_create_false_attribution(self):
        with self.assertRaisesRegex(ValueError, "required > available"):
            self.reflect(resource_shortfalls=(("food", 2.0, 3.0),))

if __name__ == "__main__":
    unittest.main()
