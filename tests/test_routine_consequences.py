"""Tests for explicit policy-driven routine consequences."""
import unittest

from simreality.routine_consequences import RoutineConsequenceAdapter, RoutineImpactPolicy
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption
from simreality.routine_world_events import RoutineWorldEventAdapter
from simreality.world_events import WorldEventLedger


class RoutineConsequenceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.block = RoutineBlock("shift", "worker", "work", "bakery", 480, 960, flexibility_minutes=30)
        book = RoutineBook((self.block,))
        disruption = RoutineDisruption(
            "traffic", "worker", DisruptionKind.TRAFFIC, 1.0, 480, 600,
            delay_minutes=20,
        )
        execution = RoutineExecutionLedger().execute(
            "9:shift", book, self.block, 500, (disruption,), outcome_sample=0.2,
        )
        self.routine_event = RoutineWorldEventAdapter(self.events).record(9, (execution,))[0]

    def test_policy_emits_consequence_event(self):
        adapter = RoutineConsequenceAdapter(self.events, (
            RoutineImpactPolicy("bakery-lateness", "work", "bakery", 10, "workplace_late_arrival"),
        ))
        result = adapter.apply((self.routine_event.event_id,))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].event_type, "workplace_late_arrival")
        attrs = dict(result[0].attributes)
        self.assertEqual(attrs["source_event_id"], self.routine_event.event_id)
        self.assertEqual(attrs["delay_minutes"], 20)
        self.assertEqual(result, adapter.apply((self.routine_event.event_id,)))

    def test_tolerance_and_unconfigured_policy_do_not_invent_consequences(self):
        tolerant = RoutineConsequenceAdapter(self.events, (
            RoutineImpactPolicy("tolerant", "work", "bakery", 30, "workplace_late_arrival"),
        ))
        self.assertEqual(tolerant.apply((self.routine_event.event_id,)), ())
        unconfigured = RoutineConsequenceAdapter(self.events, ())
        self.assertEqual(unconfigured.apply((self.routine_event.event_id,)), ())

    def test_wrong_event_type_and_duplicate_ids_rejected(self):
        adapter = RoutineConsequenceAdapter(self.events, ())
        other = self.events.append(WorldEventLedger.make_event("other", 9, "weather"))
        with self.assertRaisesRegex(ValueError, "not a routine execution"):
            adapter.apply((other.event_id,))
        with self.assertRaisesRegex(ValueError, "unique"):
            adapter.apply((self.routine_event.event_id, self.routine_event.event_id))

    def test_duplicate_policy_key_rejected(self):
        with self.assertRaisesRegex(ValueError, "one impact policy"):
            RoutineConsequenceAdapter(self.events, (
                RoutineImpactPolicy("a", "work", "bakery"),
                RoutineImpactPolicy("b", "work", "bakery"),
            ))


if __name__ == "__main__":
    unittest.main()
