import unittest

from simreality.routines import (
    DisruptionKind, RoutineBlock, RoutineBook, RoutineDisruption, RoutineOutcome,
)


class RoutineBookTests(unittest.TestCase):
    def setUp(self):
        self.work = RoutineBlock(
            "work-shift", "npc-1", "work", "shop-1", 8 * 60, 16 * 60,
            priority=0.9, flexibility_minutes=20,
            fallback_activity="call employer", fallback_location_id="home-1",
        )
        self.book = RoutineBook((self.work,))

    def test_routine_is_intention_not_guaranteed_presence(self):
        result = self.book.resolve(self.work, 8 * 60 + 5, outcome_sample=0.99)
        self.assertEqual(result.outcome, RoutineOutcome.ON_TIME)
        self.assertEqual(result.actual_location_id, "shop-1")

        alarm = RoutineDisruption(
            "phone-dead", "npc-1", DisruptionKind.ALARM_FAILURE, 1.0,
            7 * 60, 10 * 60, delay_minutes=45,
        )
        result = self.book.resolve(self.work, 8 * 60 + 5, (alarm,), outcome_sample=0.5)
        self.assertEqual(result.outcome, RoutineOutcome.REDIRECTED)
        self.assertEqual(result.actual_activity, "call employer")
        self.assertEqual(result.actual_location_id, "home-1")

    def test_traffic_weather_and_low_motivation_are_explicit_disruptions(self):
        traffic = RoutineDisruption(
            "traffic-1", "npc-1", DisruptionKind.TRAFFIC, 0.8,
            8 * 60, 10 * 60, delay_minutes=25,
        )
        weather = RoutineDisruption(
            "storm", "npc-1", DisruptionKind.WEATHER, 0.6,
            8 * 60, 10 * 60, alternative_activity="work-from-home",
            alternative_location_id="home-1",
        )
        result = self.book.resolve(self.work, 8 * 60 + 5, (traffic,), outcome_sample=0.2)
        self.assertEqual(result.outcome, RoutineOutcome.DELAYED)
        self.assertEqual(result.delay_minutes, 25)
        result = self.book.resolve(self.work, 8 * 60 + 5, (weather,), outcome_sample=0.1)
        self.assertEqual(result.outcome, RoutineOutcome.REDIRECTED)
        self.assertEqual(result.actual_activity, "work-from-home")

        lazy_day = RoutineDisruption(
            "lazy-day", "npc-1", DisruptionKind.LOW_MOTIVATION, 0.9,
            8 * 60, 10 * 60,
        )
        result = self.book.resolve(self.work, 8 * 60 + 5, (lazy_day,), outcome_sample=0.2)
        self.assertEqual(result.outcome, RoutineOutcome.REDIRECTED)
        self.assertEqual(result.actual_location_id, "home-1")

    def test_event_avoidance_can_redirect_routine(self):
        avoidance = RoutineDisruption(
            "incident-memory", "npc-1", DisruptionKind.LOCATION_AVOIDANCE, 1.0,
            0, 1440, affected_location_id="shop-1",
            alternative_activity="take-another-route", alternative_location_id="side-street",
        )
        result = self.book.resolve(self.work, 9 * 60, (avoidance,), outcome_sample=0.4)
        self.assertEqual(result.outcome, RoutineOutcome.REDIRECTED)
        self.assertEqual(result.actual_location_id, "side-street")

    def test_deterministic_under_reordered_disruptions(self):
        a = RoutineDisruption("a", "npc-1", DisruptionKind.TRAFFIC, 0.9, 480, 600, delay_minutes=10)
        b = RoutineDisruption("b", "npc-1", DisruptionKind.WEATHER, 0.8, 480, 600, delay_minutes=20)
        first = self.book.resolve(self.work, 500, (a, b), outcome_sample=0.1)
        second = self.book.resolve(self.work, 500, (b, a), outcome_sample=0.1)
        self.assertEqual(first, second)
        self.assertEqual(first.disruption_ids, ("a", "b"))

    def test_rejects_overlapping_routines_and_invalid_samples(self):
        with self.assertRaises(ValueError):
            self.book.add(RoutineBlock("overlap", "npc-1", "visit", "friend", 9 * 60, 10 * 60))
        with self.assertRaises(ValueError):
            self.book.resolve(self.work, 500, outcome_sample=1.1)
        with self.assertRaises(ValueError):
            RoutineBlock("bad", "npc-1", "sleep", "home", 600, 500)

    def test_different_npcs_can_have_overlapping_routines(self):
        other = RoutineBlock("other-work", "npc-2", "work", "office", 8 * 60, 16 * 60)
        self.book.add(other)
        self.assertEqual(len(self.book.for_period("npc-2", 500)), 1)


if __name__ == "__main__":
    unittest.main()
