import unittest

from simreality.cognitive_dissonance import (
    CognitiveDissonanceLedger, CognitiveDissonanceSnapshot,
    DissonanceDecision, DissonanceInput,
)


class CognitiveDissonanceTests(unittest.TestCase):
    def make_conflict(self, conflict_id="c1", owner="npc-a", **changes):
        values = dict(conflict_id=conflict_id, owner_id=owner, kind="belief_conflict",
                      description="Two strongly held claims cannot both be true",
                      left_reference="claim:loyalty", right_reference="claim:betrayal",
                      commitment_strength=0.9, evidence_confidence=0.8,
                      relevance=0.75, tick=4)
        values.update(changes)
        return DissonanceInput(**values)

    def test_conflict_score_uses_explicit_bounded_inputs(self):
        item = self.make_conflict()
        self.assertAlmostEqual(item.score, 0.54)
        less_committed = self.make_conflict(owner="npc-b", commitment_strength=0.4)
        self.assertAlmostEqual(less_committed.score, 0.24)

    def test_conflicts_are_owner_scoped_and_replay_safe(self):
        ledger = CognitiveDissonanceLedger()
        item = self.make_conflict()
        ledger.record(item)
        self.assertEqual(ledger.record(item), item)
        ledger.record(self.make_conflict("c2", "npc-b"))
        self.assertEqual(ledger.unresolved("npc-a"), (item,))
        with self.assertRaisesRegex(ValueError, "different content"):
            ledger.record(self.make_conflict(commitment_strength=0.1))

    def test_commitment_action_mismatch_is_explicitly_representable(self):
        item = self.make_conflict(kind="commitment_violation",
                                  description="Donated despite commitment to hoard resources",
                                  left_reference="commitment:frugality",
                                  right_reference="action:donation")
        self.assertEqual(item.kind, "commitment_violation")

    def test_response_is_history_only_and_replay_is_idempotent(self):
        ledger = CognitiveDissonanceLedger((self.make_conflict(),))
        decision = ledger.decide("d1", "c1", response="rationalize", tick=5,
                                 rationale="The circumstances were exceptional")
        self.assertEqual(ledger.decide("d1", "c1", response="rationalize", tick=5,
                                       rationale="The circumstances were exceptional"), decision)
        self.assertEqual(ledger.unresolved("npc-a"), ())
        self.assertEqual(ledger.decision_for("c1"), decision)
        with self.assertRaisesRegex(ValueError, "already has"):
            ledger.decide("d2", "c1", response="reconsider", tick=6)

    def test_response_cannot_precede_conflict_or_change_owner(self):
        ledger = CognitiveDissonanceLedger((self.make_conflict(),))
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            ledger.decide("d1", "c1", response="acknowledge", tick=3)
        wrong_owner = DissonanceDecision("d2", "c1", "npc-b", "acknowledge", 5, "")
        with self.assertRaisesRegex(ValueError, "owner"):
            ledger._store_decision(wrong_owner)

    def test_snapshot_round_trip_preserves_conflicts_and_decisions(self):
        ledger = CognitiveDissonanceLedger((self.make_conflict(), self.make_conflict("c2", "npc-b")))
        ledger.decide("d1", "c1", response="seek_evidence", tick=5, rationale="Need more context")
        encoded = CognitiveDissonanceSnapshot.capture(ledger).to_json()
        restored = CognitiveDissonanceSnapshot.from_json(encoded).restore()
        self.assertEqual(restored.conflicts(), ledger.conflicts())
        self.assertEqual(restored.decisions(), ledger.decisions())
        self.assertEqual(CognitiveDissonanceSnapshot.capture(restored).to_json(), encoded)

    def test_snapshot_rejects_noncanonical_json(self):
        encoded = CognitiveDissonanceSnapshot.capture(CognitiveDissonanceLedger()).to_json()
        with self.assertRaisesRegex(ValueError, "canonical"):
            CognitiveDissonanceSnapshot.from_json(encoded + " ")


if __name__ == "__main__":
    unittest.main()
