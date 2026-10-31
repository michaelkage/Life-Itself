import unittest

from simreality.institutional_politics import InstitutionalPoliticalEvent, InstitutionalPoliticalLedger
from simreality.institutional_lobbying import (
    InstitutionalLobbyEvaluator,
    PoliticalLobbyPolicy,
    PoliticalLobbyRequest,
)


class InstitutionalLobbyingTests(unittest.TestCase):
    def setUp(self):
        self.ledger = InstitutionalPoliticalLedger(
            "city_hall",
            initial_influence=(("planning", 0.8), ("transport", 0.9), ("housing", 0.9)),
            leadership_priorities=(("housing", 0.3),),
        )
        self.policy = PoliticalLobbyPolicy("civic-accountability")
        self.evaluator = InstitutionalLobbyEvaluator()

    def request(self, request_id="housing-plan", **kwargs):
        values = dict(
            request_id=request_id,
            institution_id="city_hall",
            period_index=2,
            department_id="planning",
            priority_tag="housing",
            requested_priority_delta=0.2,
            service_impact=1.0,
            evidence_strength=1.0,
            transparency=1.0,
            public_visibility=0.5,
            urgency=0.8,
        )
        values.update(kwargs)
        return PoliticalLobbyRequest(**values)

    def test_strong_evidence_and_service_value_can_win_approval(self):
        result = self.evaluator.assess(self.ledger, self.request(), self.policy)
        self.assertEqual(result.decision, "approved")
        self.assertGreaterEqual(result.score, self.policy.approval_threshold)

    def test_low_evidence_and_low_service_value_are_rejected(self):
        result = self.evaluator.assess(
            self.ledger,
            self.request("weak", service_impact=0.0, evidence_strength=0.0,
                         transparency=0.0, urgency=0.0, public_visibility=0.0,
                         personal_advantage=1.0),
            self.policy,
        )
        self.assertEqual(result.decision, "rejected")
        self.assertEqual(result.event.leadership_priority_delta, 0.0)
        self.assertLess(result.event.influence_delta, 0.0)

    def test_allied_departments_strengthen_coalition_support(self):
        self.ledger.append(InstitutionalPoliticalEvent(
            "alliance", "city_hall", 1, "planning",
            other_department_id="transport", relationship_delta=1.0,
            influence_delta=0.0,
        ))
        neutral = self.evaluator.assess(self.ledger, self.request(), self.policy)
        allied = self.evaluator.assess(
            self.ledger,
            self.request("allied", supporting_departments=("transport",)),
            self.policy,
        )
        self.assertGreater(allied.coalition_score, neutral.coalition_score)
        self.assertGreater(allied.score, neutral.score)

    def test_opposing_rival_department_reduces_coalition_pressure(self):
        self.ledger.append(InstitutionalPoliticalEvent(
            "rivalry", "city_hall", 1, "planning",
            other_department_id="transport", relationship_delta=-1.0,
            influence_delta=0.0,
        ))
        neutral = self.evaluator.assess(self.ledger, self.request(), self.policy)
        opposed = self.evaluator.assess(
            self.ledger,
            self.request("opposed", opposing_departments=("transport",)),
            self.policy,
        )
        self.assertLess(opposed.coalition_score, neutral.coalition_score)

    def test_commit_changes_priority_and_department_influence(self):
        assessment = self.evaluator.assess(self.ledger, self.request(), self.policy)
        before = self.ledger.state()
        self.evaluator.commit(self.ledger, (assessment,))
        after = self.ledger.state()
        self.assertAlmostEqual(
            dict(after.leadership_priorities)["housing"],
            dict(before.leadership_priorities)["housing"] + 0.2,
        )
        self.assertAlmostEqual(
            dict(after.department_influence)["planning"],
            dict(before.department_influence)["planning"] + 0.04,
        )
        # Re-appending the exact same committed event is idempotent.
        self.evaluator.commit(self.ledger, (assessment,))
        self.assertEqual(len(self.ledger.events), 1)

    def test_reusing_request_id_with_changed_inputs_is_rejected(self):
        original = self.evaluator.assess(self.ledger, self.request(), self.policy)
        changed = self.evaluator.assess(
            self.ledger,
            self.request(service_impact=0.9),
            self.policy,
        )
        self.evaluator.commit(self.ledger, (original,))
        with self.assertRaises(ValueError):
            self.evaluator.commit(self.ledger, (changed,))

    def test_deferred_request_does_not_change_leadership_priority(self):
        policy = PoliticalLobbyPolicy(
            "strict", approval_threshold=0.95, defer_threshold=0.1,
        )
        assessment = self.evaluator.assess(self.ledger, self.request(), policy)
        self.assertEqual(assessment.decision, "deferred")
        self.assertEqual(assessment.event.leadership_priority_delta, 0.0)
        self.assertEqual(assessment.event.influence_delta, 0.0)

    def test_batch_assessment_uses_same_pre_resolution_state(self):
        first = self.request("a")
        second = self.request("b", department_id="housing")
        before = self.ledger.state()
        results = self.evaluator.assess_many(self.ledger, (second, first), self.policy)
        self.assertEqual(tuple(x.request_id for x in results), ("a", "b"))
        expected = {
            "a": self.evaluator.assess(self.ledger, first, self.policy).score,
            "b": self.evaluator.assess(self.ledger, second, self.policy).score,
        }
        self.assertEqual({x.request_id: x.score for x in results}, expected)
        self.assertEqual(self.ledger.state(), before)

    def test_invalid_requests_and_duplicate_batch_departments_rejected(self):
        with self.assertRaises(ValueError):
            self.request("bad", supporting_departments=("planning",))
        with self.assertRaises(ValueError):
            self.evaluator.assess_many(
                self.ledger, (self.request("a"), self.request("b")), self.policy,
            )
        with self.assertRaises(ValueError):
            self.evaluator.assess(
                self.ledger, self.request(institution_id="court"), self.policy,
            )


if __name__ == "__main__":
    unittest.main()
