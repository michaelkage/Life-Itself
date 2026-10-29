"""Regression tests for routine scheduling at explicit simulation ticks."""
import unittest

from simreality.routines import (
    DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption, RoutineOutcome,
)
from simreality.routine_tick import RoutineTickAdapter


class RoutineTickAdapterTests(unittest.TestCase):
    def setUp(self):
        self.book = RoutineBook((
            RoutineBlock("work-a", "npc-a", "work", "office", 480, 960),
            RoutineBlock("shop-b", "npc-b", "open_shop", "shop", 540, 1020),
            RoutineBlock("sleep-c", "npc-c", "sleep", "home", 0, 420),
        ))
        self.disruption = RoutineDisruption(
            "traffic-a", "npc-a", DisruptionKind.TRAFFIC, 1.0, 540, 600,
            affected_location_id="office", delay_minutes=25,
        )
        self.adapter = RoutineTickAdapter()

    def test_executes_only_active_routines_in_stable_order(self):
        result = self.adapter.execute_due(
            "tick-9", self.book, 550,
            outcome_samples={"work-a": 0.0, "shop-b": 0.9},
        )
        self.assertEqual([r.routine_id for r in result], ["shop-b", "work-a"])

    def test_disruption_is_scoped_to_owning_npc(self):
        result = self.adapter.execute_due(
            "tick-9", self.book, 550,
            disruptions=(self.disruption,),
            outcome_samples={"work-a": 0.0, "shop-b": 0.0},
        )
        by_id = {r.routine_id: r.resolution for r in result}
        self.assertEqual(by_id["work-a"].outcome, RoutineOutcome.DELAYED)
        self.assertEqual(by_id["shop-b"].outcome, RoutineOutcome.ON_TIME)

    def test_retry_returns_same_ledger_records(self):
        args = {"outcome_samples": {"work-a": 0.0, "shop-b": 0.0}}
        first = self.adapter.execute_due("tick-9", self.book, 550, **args)
        second = self.adapter.execute_due("tick-9", self.book, 550, **args)
        self.assertEqual(first, second)
        self.assertIs(first[0], second[0])

    def test_conflicting_retry_rejected_by_execution_id(self):
        self.adapter.execute_due(
            "tick-9", self.book, 550,
            outcome_samples={"work-a": 0.0, "shop-b": 0.0},
        )
        with self.assertRaises(ValueError):
            self.adapter.execute_due(
                "tick-9", self.book, 550,
                outcome_samples={"work-a": 1.0, "shop-b": 0.0},
            )

    def test_requires_explicit_sample_for_each_active_routine(self):
        with self.assertRaisesRegex(ValueError, "missing outcome sample"):
            self.adapter.execute_due("tick-9", self.book, 550, outcome_samples={"work-a": 0.0})

    def test_owner_filter_and_invalid_duplicate_disruptions(self):
        result = self.adapter.execute_due(
            "tick-9", self.book, 550, owner_ids=("npc-a",),
            outcome_samples={"work-a": 0.0, "shop-b": 0.0},
        )
        self.assertEqual([r.routine_id for r in result], ["work-a"])
        with self.assertRaisesRegex(ValueError, "unique"):
            self.adapter.execute_due(
                "tick-10", self.book, 550,
                disruptions=(self.disruption, self.disruption),
                outcome_samples={"work-a": 0.0, "shop-b": 0.0},
            )


if __name__ == "__main__":
    unittest.main()
