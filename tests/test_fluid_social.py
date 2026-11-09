import struct
import unittest

from simreality.fluid_social import (
    ClaimEvidenceBatch, EvidenceEdge, evaluate_gather_cpu,
    pack_evidence_gather, unpack_gather_outputs,
)


class FluidSocialGatherTests(unittest.TestCase):
    def edge(self, evidence_id, tick, direction=1, strength=0.8, reliability=0.75):
        return EvidenceEdge(evidence_id, tick, strength, reliability, direction)

    def test_packing_is_canonical_and_uses_fixed_strides(self):
        batches = (
            ClaimEvidenceBatch("z-claim", 0.5, (self.edge("late", 2), self.edge("early", 1))),
            ClaimEvidenceBatch("a-claim", 0.25, ()),
        )
        slots, edges, ids = pack_evidence_gather(batches)
        self.assertEqual(ids, ("a-claim", "z-claim"))
        self.assertEqual(len(slots), 2 * 32)
        self.assertEqual(len(edges), 2 * 16)
        self.assertEqual(struct.unpack_from("<4I4f", slots, 32)[:2], (0, 2))
        self.assertEqual(struct.unpack_from("<4f", edges, 0)[2], 1.0)

    def test_gather_matches_authoritative_belief_recurrence(self):
        batch = ClaimEvidenceBatch("claim", 0.5, (
            self.edge("later-support", 2, 1, 0.8, 0.9),
            self.edge("early-contradiction", 1, -1, 0.4, 0.75),
        ))
        result = evaluate_gather_cpu((batch,))[0]
        confidence = 0.5
        confidence += (0.0 - confidence) * (0.4 * 0.75)
        confidence += (1.0 - confidence) * (0.8 * 0.9)
        self.assertAlmostEqual(result.confidence, confidence)
        self.assertEqual(result.evidence_count, 2)

    def test_input_order_does_not_change_canonical_result(self):
        first = ClaimEvidenceBatch("claim", 0.5, (
            self.edge("b", 4, 1), self.edge("a", 2, -1)))
        second = ClaimEvidenceBatch("claim", 0.5, (
            self.edge("a", 2, -1), self.edge("b", 4, 1)))
        self.assertEqual(evaluate_gather_cpu((first,)), evaluate_gather_cpu((second,)))
        self.assertEqual(pack_evidence_gather((first,))[:2],
                         pack_evidence_gather((second,))[:2])

    def test_output_decoder_restores_claim_ids_and_rejects_malformed_data(self):
        packed = struct.pack("<4f", 0.75, 2.0, 0.0, 0.0)
        self.assertEqual(unpack_gather_outputs(("claim",), packed)[0].evidence_count, 2)
        with self.assertRaises(ValueError):
            unpack_gather_outputs(("claim",), packed[:-1])
        with self.assertRaises(ValueError):
            unpack_gather_outputs(("claim",), struct.pack("<4f", 1.2, 1.0, 0.0, 0.0))

    def test_invalid_edges_and_claim_batches_are_rejected(self):
        with self.assertRaises(ValueError):
            self.edge("bad", -1)
        with self.assertRaises(ValueError):
            self.edge("bad", 1, direction=0)
        with self.assertRaises(ValueError):
            ClaimEvidenceBatch("claim", 1.2)
        with self.assertRaises(ValueError):
            ClaimEvidenceBatch("claim", 0.5, (self.edge("same", 1), self.edge("same", 2)))
        with self.assertRaises(ValueError):
            pack_evidence_gather((ClaimEvidenceBatch("same", 0.5),
                                  ClaimEvidenceBatch("same", 0.4)))


if __name__ == "__main__":
    unittest.main()
