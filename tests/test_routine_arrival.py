"""Arrival-gated routine execution regression coverage."""
import unittest

from simreality.routine_arrival import RoutineArrivalAdapter
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import RoutineBlock, RoutineBook, RoutineOutcome
from simreality.travel import TravelJourney, TravelLedger
from simreality.world_events import WorldEventLedger
from simreality.routine_world_events import RoutineWorldEventAdapter


class RoutineArrivalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.block = RoutineBlock(
            "shift", "npc", "work", "office", 540, 600,
            flexibility_minutes=15, fallback_activity="work_from_home",
            fallback_location_id="home",
        )
        self.book = RoutineBook((self.block,))
        self.travel = TravelLedger((TravelJourney(
            "commute", "npc", "home", "office", ("home", "office"),
            ("road",), edge_index=1, status="arrived", started_tick=1,
            arrived_tick=3, routine_id="shift",
        ),))
        self.ledger = RoutineExecutionLedger()
        self.adapter = RoutineArrivalAdapter(self.ledger)

    def process(self, minute, **kwargs):
        return self.adapter.process(
            3, minute, self.book, self.travel,
            outcome_samples={"shift": 0.25}, **kwargs,
        )

    def test_early_arrival_waits_without_execution(self):
        result = self.process(530)
        self.assertEqual(result[0].status, "waiting")
        self.assertIsNone(result[0].execution)
        self.assertEqual(self.ledger.snapshot(), ())

    def test_on_time_arrival_executes_and_emits_world_event(self):
        events = WorldEventLedger()
        adapter = RoutineWorldEventAdapter(events)
        result = self.process(540, world_events=adapter)
        self.assertEqual(result[0].status, "executed")
        self.assertEqual(result[0].execution.resolution.outcome, RoutineOutcome.ON_TIME)
        self.assertEqual(events.query(event_type="routine_execution")[0].tick, 3)

    def test_late_arrival_within_flexibility_is_delayed(self):
        result = self.process(550)
        self.assertEqual(result[0].execution.resolution.outcome, RoutineOutcome.DELAYED)
        self.assertEqual(result[0].execution.resolution.delay_minutes, 10)

    def test_late_arrival_beyond_flexibility_uses_explicit_fallback(self):
        result = self.process(570)
        resolution = result[0].execution.resolution
        self.assertEqual(resolution.outcome, RoutineOutcome.REDIRECTED)
        self.assertEqual(resolution.actual_activity, "work_from_home")
        self.assertEqual(resolution.actual_location_id, "home")

    def test_arrival_after_end_is_missed_or_redirected(self):
        result = self.process(610)
        self.assertEqual(result[0].execution.resolution.outcome, RoutineOutcome.REDIRECTED)
        no_fallback = RoutineBook((RoutineBlock("shift", "npc", "work", "office", 540, 600),))
        result = RoutineArrivalAdapter(RoutineExecutionLedger()).process(
            4, 610, no_fallback, self.travel,
            outcome_samples={"shift": 0.25},
        )
        self.assertEqual(result[0].status, "missed")
        self.assertEqual(result[0].execution.resolution.outcome, RoutineOutcome.MISSED)

    def test_replay_is_idempotent_and_conflicting_minute_rejected(self):
        first = self.process(550)[0]
        second = self.process(550)[0]
        self.assertEqual(first, second)
        self.assertEqual(second.status, "already_executed")
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.process(551)

    def test_later_ticks_do_not_execute_the_same_arrived_journey_again(self):
        first = self.process(550)[0]
        later = self.adapter.process(
            4, 551, self.book, self.travel,
            outcome_samples={"shift": 0.75},
        )[0]
        self.assertEqual(first.status, "executed")
        self.assertEqual(later.status, "already_executed")
        self.assertEqual(later.execution, first.execution)
        self.assertEqual(len(self.ledger.snapshot()), 1)

    def test_non_arrived_and_non_routine_journeys_are_ignored(self):
        travel = TravelLedger((TravelJourney(
            "other", "another", "a", "b", ("a", "b"), ("road",),
            status="travelling", started_tick=1,
        ),))
        self.assertEqual(self.adapter.process(
            3, 550, self.book, travel, outcome_samples={},
        ), ())


if __name__ == "__main__":
    unittest.main()
