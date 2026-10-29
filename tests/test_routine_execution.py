import unittest

from simreality.routines import DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption, RoutineOutcome
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routine_execution_save_state import RoutineExecutionSnapshot


class RoutineExecutionLedgerTests(unittest.TestCase):
    def setUp(self):
        self.block = RoutineBlock("shift", "npc-1", "work", "shop", 480, 960,
                                  flexibility_minutes=10, fallback_activity="call manager",
                                  fallback_location_id="home")
        self.book = RoutineBook((self.block,))
        self.traffic = RoutineDisruption("traffic", "npc-1", DisruptionKind.TRAFFIC,
                                         1.0, 480, 600, delay_minutes=20)

    def test_execution_is_idempotent_and_conflicting_reuse_is_rejected(self):
        ledger = RoutineExecutionLedger()
        first = ledger.execute("exec-1", self.book, self.block, 500, (self.traffic,), outcome_sample=0.2)
        replay = ledger.execute("exec-1", self.book, self.block, 500, (self.traffic,), outcome_sample=0.2)
        self.assertEqual(first, replay)
        self.assertEqual(first.resolution.outcome, RoutineOutcome.REDIRECTED)
        with self.assertRaisesRegex(ValueError, "conflicting routine execution ID"):
            ledger.execute("exec-1", self.book, self.block, 500, (), outcome_sample=0.2)

    def test_identical_replay_returns_stored_result_without_resolving_again(self):
        ledger = RoutineExecutionLedger()
        first = ledger.execute("exec-1", self.book, self.block, 500,
                               (self.traffic,), outcome_sample=0.2)

        def unexpected_resolve(*args, **kwargs):
            raise AssertionError("identical replay should use the stored result")

        self.book.resolve = unexpected_resolve
        replay = ledger.execute("exec-1", self.book, self.block, 500,
                                (self.traffic,), outcome_sample=0.2)
        self.assertIs(replay, first)

    def test_same_id_with_different_routine_identity_is_rejected(self):
        ledger = RoutineExecutionLedger()
        ledger.execute("exec-1", self.book, self.block, 500, (), outcome_sample=0.2)
        changed = RoutineBlock("shift", "npc-1", "visit friend", "friend-home", 480, 960)
        with self.assertRaisesRegex(ValueError, "conflicting routine execution ID"):
            ledger.execute("exec-1", self.book, changed, 500, (), outcome_sample=0.2)

    def test_reordered_disruptions_have_same_execution_signature(self):
        second = RoutineDisruption("weather", "npc-1", DisruptionKind.WEATHER,
                                   1.0, 480, 600, delay_minutes=25)
        ledger = RoutineExecutionLedger()
        first = ledger.execute("exec-1", self.book, self.block, 500,
                               (second, self.traffic), outcome_sample=0.2)
        replay = ledger.execute("exec-1", self.book, self.block, 500,
                                (self.traffic, second), outcome_sample=0.2)
        self.assertEqual(first, replay)

    def test_execution_snapshot_round_trip_preserves_exact_results(self):
        ledger = RoutineExecutionLedger()
        ledger.execute("exec-2", self.book, self.block, 500, (self.traffic,), outcome_sample=0.2)
        ledger.execute("exec-1", self.book, self.block, 500, (), outcome_sample=0.99)
        snapshot = RoutineExecutionSnapshot.capture(ledger)
        payload = snapshot.to_json()
        restored = RoutineExecutionSnapshot.from_json(payload).restore()
        self.assertEqual(restored.snapshot(), ledger.snapshot())
        before = restored.get("exec-2")
        replay = restored.execute("exec-2", self.book, self.block, 500,
                                  (self.traffic,), outcome_sample=0.2)
        self.assertEqual(replay, before)
        self.assertEqual(RoutineExecutionSnapshot.capture(restored).to_json(), payload)

    def test_rejects_unknown_schema_and_noncanonical_json(self):
        with self.assertRaises(ValueError):
            RoutineExecutionSnapshot.from_json('{"schema_version":9,"records":[]}')
        with self.assertRaisesRegex(ValueError, "canonical JSON"):
            RoutineExecutionSnapshot.from_json('{ "schema_version": 1, "records": [] }')


if __name__ == "__main__":
    unittest.main()
