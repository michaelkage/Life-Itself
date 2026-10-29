"""Tests for routine outcome materialization in the authoritative event journal."""
import unittest

from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption
from simreality.routine_world_events import RoutineWorldEventAdapter
from simreality.world_events import WorldEventLedger


class RoutineWorldEventAdapterTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.adapter = RoutineWorldEventAdapter(self.events)
        self.block = RoutineBlock("shift-1", "npc-1", "work", "bakery", 480, 960, flexibility_minutes=30)
        self.book = RoutineBook((self.block,))
        self.ledger = RoutineExecutionLedger()

    def execution(self, sample=0.0, disruptions=()):
        return self.ledger.execute(
            "7:shift-1", self.book, self.block, 500, disruptions,
            outcome_sample=sample,
        )

    def test_outcome_becomes_queryable_world_event(self):
        traffic = RoutineDisruption(
            "traffic-1", "npc-1", DisruptionKind.TRAFFIC, 1.0,
            480, 600, delay_minutes=20,
        )
        execution = self.execution(0.2, (traffic,))
        event = self.adapter.record(7, (execution,), witnesses_by_execution={
            execution.execution_id: ("witness-1",),
        })[0]
        self.assertEqual(event.event_id, "routine:7:shift-1")
        self.assertEqual(event.event_type, "routine_execution")
        self.assertEqual(event.participants, ("npc-1",))
        self.assertEqual(event.witnesses, ("witness-1",))
        attrs = dict(event.attributes)
        self.assertEqual(attrs["outcome"], "delayed")
        self.assertEqual(attrs["delay_minutes"], 20)
        self.assertEqual(attrs["actual_location_id"], "bakery")
        self.assertEqual(self.events.query(witness_id="witness-1"), (event,))

    def test_reordered_batch_and_retry_are_idempotent(self):
        first = self.execution()
        second_block = RoutineBlock("appointment-2", "npc-2", "appointment", "clinic", 480, 600)
        second_book = RoutineBook((second_block,))
        second = RoutineExecutionLedger().execute(
            "7:appointment-2", second_book, second_block, 500, outcome_sample=0.0,
        )
        forward = self.adapter.record(7, (first, second))
        reverse = self.adapter.record(7, (second, first))
        self.assertEqual(forward, reverse)
        self.assertEqual(len(self.events), 2)

    def test_conflicting_tick_reuse_rejected(self):
        execution = self.execution()
        self.adapter.record(7, (execution,))
        with self.assertRaisesRegex(ValueError, "different content"):
            self.adapter.record(8, (execution,))

    def test_unknown_witness_mapping_rejected(self):
        execution = self.execution()
        with self.assertRaisesRegex(ValueError, "unknown execution ID"):
            self.adapter.record(7, (execution,), witnesses_by_execution={"missing": ("w",)})

    def test_invalid_or_duplicate_inputs_rejected(self):
        execution = self.execution()
        with self.assertRaises(ValueError):
            self.adapter.record(-1, (execution,))
        with self.assertRaisesRegex(ValueError, "unique"):
            self.adapter.record(7, (execution, execution))


if __name__ == "__main__":
    unittest.main()
