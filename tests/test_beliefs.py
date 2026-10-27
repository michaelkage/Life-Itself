"""Regression tests for deterministic evidence-based NPC belief updates."""
import unittest

from simreality.beliefs import BeliefLedger, Evidence


def evidence(eid, direction, tick=1, strength=1.0, reliability=1.0, claim="saw-event"):
    return Evidence(eid, claim, "witness", direction, strength, reliability, tick)


class BeliefLedgerTests(unittest.TestCase):
    def test_support_and_contradiction_move_confidence_in_opposite_directions(self):
        ledger = BeliefLedger({"saw-event": 0.5})
        supported = ledger.add(evidence("e1", 1))
        self.assertEqual(supported.confidence, 1.0)
        contradicted = ledger.add(evidence("e2", -1, tick=2))
        self.assertEqual(contradicted.confidence, 0.0)

    def test_initial_prior_is_preserved_as_evidence_baseline(self):
        ledger = BeliefLedger({"saw-event": 0.2})
        result = ledger.add(evidence("partial", 1, strength=0.5, reliability=0.5))
        self.assertAlmostEqual(result.confidence, 0.4)

    def test_strength_and_source_reliability_scale_influence(self):
        ledger = BeliefLedger({"saw-event": 0.5})
        result = ledger.add(evidence("weak", 1, strength=0.5, reliability=0.4))
        self.assertAlmostEqual(result.confidence, 0.6)

    def test_batch_order_is_canonical_and_reproducible(self):
        items = [evidence("b", -1, tick=2, strength=0.4),
                 evidence("a", 1, tick=1, strength=0.6)]
        first, second = BeliefLedger(), BeliefLedger()
        first.add_many(items)
        second.add_many(reversed(items))
        self.assertEqual(first.snapshot(), second.snapshot())

    def test_duplicate_identical_evidence_is_idempotent(self):
        ledger = BeliefLedger()
        item = evidence("same", 1, strength=0.5)
        once = ledger.add(item)
        twice = ledger.add(item)
        self.assertEqual(once, twice)

    def test_evidence_id_cannot_be_reused_for_different_content(self):
        ledger = BeliefLedger()
        ledger.add(evidence("same", 1))
        with self.assertRaises(ValueError):
            ledger.add(evidence("same", -1))

    def test_claims_are_independent_and_snapshot_is_stably_sorted(self):
        ledger = BeliefLedger()
        ledger.add(evidence("z", 1, claim="z-claim"))
        ledger.add(evidence("a", -1, claim="a-claim"))
        self.assertEqual([s.claim_id for s in ledger.snapshot()], ["a-claim", "z-claim"])

    def test_invalid_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            Evidence("e", "claim", "source", 0, 0.5, 0.5, 1)
        with self.assertRaises(ValueError):
            Evidence("e", "claim", "source", 1, 1.1, 0.5, 1)
        with self.assertRaises(ValueError):
            Evidence("e", "claim", "source", 1, 0.5, 0.5, -1)


if __name__ == "__main__":
    unittest.main()
