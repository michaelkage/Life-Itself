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


if __name__ == "__main__":
    unittest.main()
