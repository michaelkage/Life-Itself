"""Durable whole-tick transaction journal tests."""
import json
import tempfile
import unittest
from pathlib import Path

from simreality.population_transaction import (
    PopulationTickTransactionCoordinator,
    TransactionParticipant,
)


class PopulationTickTransactionTests(unittest.TestCase):
    def participant(self, name, state):
        def capture():
            return json.dumps(state, sort_keys=True)
        def restore(payload):
            state.clear()
            state.update(json.loads(payload))
        return TransactionParticipant(name, capture, restore)

    def test_failed_tick_restores_every_participant(self):
        with tempfile.TemporaryDirectory() as directory:
            first = {"events": ["before"]}
            second = {"money": 50}
            coordinator = PopulationTickTransactionCoordinator(
                Path(directory) / "ticks.json",
                (self.participant("events", first), self.participant("economy", second)),
            )

            def fail():
                first["events"].append("partial")
                second["money"] = 0
                raise RuntimeError("forced phase failure")

            with self.assertRaisesRegex(RuntimeError, "forced phase failure"):
                coordinator.execute(4, {"input": "same"}, fail)

            self.assertEqual(first, {"events": ["before"]})
            self.assertEqual(second, {"money": 50})
            self.assertEqual(coordinator.journal_snapshot()[0]["status"], "aborted")

    def test_committed_checkpoint_recovers_after_restart_and_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            live = {"events": [], "balances": {"household": 100}}
            first = PopulationTickTransactionCoordinator(
                journal,
                (self.participant("world", live),),
            )

            def apply_once():
                if 9 not in live["events"]:
                    live["events"].append(9)
                    live["balances"]["household"] -= 25
                return {"tick": 9, "balance": live["balances"]["household"]}

            result = first.execute(9, {"tick": 9, "event": "wage"}, apply_once)
            self.assertEqual(result, {"tick": 9, "balance": 75})
            saved_result = first.journal_snapshot()[0]["result_payload"]
            self.assertEqual(json.loads(saved_result), result)

            restarted_state = {"events": [], "balances": {"household": 0}}
            restarted = PopulationTickTransactionCoordinator(
                journal,
                (self.participant("world", restarted_state),),
            )
            self.assertEqual(restarted_state, live)
            replay = restarted.execute(9, {"tick": 9, "event": "wage"}, apply_once)
            self.assertEqual(replay, result)
            self.assertEqual(restarted_state["events"], [9])
            self.assertEqual(restarted_state["balances"]["household"], 75)

    def test_conflicting_durable_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"value": 0}
            coordinator = PopulationTickTransactionCoordinator(
                Path(directory) / "ticks.json",
                (self.participant("state", state),),
            )
            coordinator.execute(1, {"amount": 10}, lambda: state.update(value=10))
            with self.assertRaisesRegex(ValueError, "different inputs"):
                coordinator.execute(1, {"amount": 11}, lambda: state.update(value=11))

    def test_non_json_participant_checkpoint_is_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"value": 0}
            participant = TransactionParticipant("bad", lambda: "{not-json", lambda _: None)
            coordinator = PopulationTickTransactionCoordinator(
                Path(directory) / "ticks.json", (participant,),
            )
            with self.assertRaises(json.JSONDecodeError):
                coordinator.execute(1, {}, lambda: state.update(value=1))
            self.assertEqual(state, {"value": 0})


    def test_rolled_back_tick_can_retry_same_request(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {"count": 0}
            coordinator = PopulationTickTransactionCoordinator(
                Path(directory) / "ticks.json", (self.participant("state", state),),
            )
            def fail_once():
                state["count"] += 1
                raise RuntimeError("transient")
            with self.assertRaisesRegex(RuntimeError, "transient"):
                coordinator.execute(2, {"seed": 7}, fail_once)
            result = coordinator.execute(2, {"seed": 7}, lambda: state.update(count=state["count"] + 1))
            self.assertIsNone(result)
            self.assertEqual(state["count"], 1)

    def test_startup_recovers_interrupted_prepared_tick_to_pre_tick_state(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            journal.write_text(json.dumps({
                "schema_version": 1,
                "records": [{
                    "tick": 3, "request_signature": "a" * 64, "status": "prepared",
                    "before": {"state": json.dumps({"count": 5})},
                    "after": {}, "result_digest": None, "result_payload": None,
                }],
            }), encoding="utf-8")
            live = {"count": 99}
            coordinator = PopulationTickTransactionCoordinator(
                journal, (self.participant("state", live),),
            )
            self.assertEqual(live, {"count": 5})
            self.assertEqual(coordinator.journal_snapshot()[0]["status"], "aborted")

    def test_independent_coordinators_reload_journal_under_shared_process_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            first_state = {"events": [], "balance": 0}
            second_state = {"events": [], "balance": 0}
            first = PopulationTickTransactionCoordinator(
                journal, (self.participant("world", first_state),),
            )
            second = PopulationTickTransactionCoordinator(
                journal, (self.participant("world", second_state),),
            )
            first.execute(1, {"event": "first"}, lambda: (
                first_state["events"].append("first"),
                first_state.update(balance=first_state["balance"] + 10),
            ))
            second.execute(2, {"event": "second"}, lambda: (
                second_state["events"].append("second"),
                second_state.update(balance=second_state["balance"] + 5),
            ))
            records = first.journal_snapshot()
            self.assertEqual(tuple(item["tick"] for item in records), (1, 2))
            self.assertEqual(first_state, {"events": ["first", "second"], "balance": 15})
            self.assertEqual(second_state, first_state)

    def test_commit_fsync_failure_requires_recovery_without_rolling_back_durable_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            state = {"balance": 0}
            coordinator = PopulationTickTransactionCoordinator(
                journal, (self.participant("economy", state),),
            )
            persist = coordinator._persist
            calls = 0

            def persist_then_fail_commit():
                nonlocal calls
                calls += 1
                persist()
                if calls == 2:
                    raise OSError("simulated directory fsync failure after atomic replace")

            coordinator._persist = persist_then_fail_commit
            with self.assertRaisesRegex(OSError, "directory fsync failure"):
                coordinator.execute(
                    1, {"wage": 20},
                    lambda: state.update(balance=state["balance"] + 20),
                )
            self.assertEqual(state["balance"], 20)
            with self.assertRaisesRegex(RuntimeError, "requires journal recovery"):
                coordinator.execute(2, {}, lambda: None)

            recovered_state = {"balance": -1}
            recovered = PopulationTickTransactionCoordinator(
                journal, (self.participant("economy", recovered_state),),
            )
            self.assertEqual(recovered_state["balance"], 20)
            self.assertEqual(recovered.journal_snapshot()[0]["status"], "committed")

    def test_journal_lock_timeout_is_bounded(self):
        import time
        try:
            import fcntl
        except ImportError:
            self.skipTest("POSIX flock timeout test")
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            coordinator = PopulationTickTransactionCoordinator(
                journal, (self.participant("state", {"value": 0}),),
                lock_timeout_seconds=0.1,
            )
            lock_path = journal.with_name(journal.name + ".lock")
            with open(lock_path, "a+b") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                started = time.monotonic()
                with self.assertRaisesRegex(TimeoutError, "population journal lock"):
                    coordinator.execute(1, {}, lambda: None)
                self.assertLess(time.monotonic() - started, 1.0)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def test_committed_result_digest_corruption_is_rejected_on_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "ticks.json"
            state = {"count": 0}
            participants = (self.participant("state", state),)
            coordinator = PopulationTickTransactionCoordinator(journal, participants)
            coordinator.execute(1, {"tick": 1}, lambda: state.update(count=1))
            payload = json.loads(journal.read_text(encoding="utf-8"))
            payload["records"][0]["result_digest"] = "0" * 64
            journal.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "result digest mismatch"):
                PopulationTickTransactionCoordinator(journal, participants)

if __name__ == "__main__":
    unittest.main()
