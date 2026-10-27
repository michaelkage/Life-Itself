"""Regression tests for the append-only world event journal."""
import unittest

from simreality.world_events import WorldEvent, WorldEventLedger


class WorldEventLedgerTests(unittest.TestCase):
    def event(self, event_id, tick, **kwargs):
        return WorldEventLedger.make_event(event_id, tick, "interaction", **kwargs)

    def test_snapshot_order_does_not_depend_on_ingestion_order(self):
        first = self.event("later-id", 4, participants=("actor",))
        second = self.event("earlier-tick", 2, participants=("witness",))
        ledger = WorldEventLedger((first, second))
        self.assertEqual(tuple(e.event_id for e in ledger.snapshot()), ("earlier-tick", "later-id"))

    def test_identical_replay_is_idempotent(self):
        ledger = WorldEventLedger()
        event = self.event("event-1", 5, participants=("actor",))
        ledger.append(event)
        ledger.append(event)
        self.assertEqual(len(ledger), 1)

    def test_conflicting_id_is_rejected(self):
        ledger = WorldEventLedger((self.event("event-1", 5, participants=("actor",)),))
        with self.assertRaises(ValueError):
            ledger.append(self.event("event-1", 6, participants=("actor",)))
        self.assertEqual(len(ledger), 1)

    def test_batch_conflict_is_atomic(self):
        ledger = WorldEventLedger()
        one = self.event("event-1", 1)
        conflict_a = self.event("event-2", 2)
        conflict_b = self.event("event-2", 3)
        with self.assertRaises(ValueError):
            ledger.append_many((one, conflict_a, conflict_b))
        self.assertEqual(len(ledger), 0)

    def test_query_filters_and_inclusive_tick_bounds(self):
        ledger = WorldEventLedger((
            self.event("one", 1, participants=("actor",), witnesses=("witness",)),
            self.event("two", 2, participants=("actor",), event_type="arrest"),
            self.event("three", 3, participants=("other",), witnesses=("witness",)),
        ))
        result = ledger.query(start_tick=1, end_tick=2, participant_id="actor")
        self.assertEqual(tuple(e.event_id for e in result), ("one", "two"))
        self.assertEqual(tuple(e.event_id for e in ledger.query(witness_id="witness")), ("one", "three"))
        self.assertEqual(tuple(e.event_id for e in ledger.query(event_type="arrest")), ("two",))

    def test_attribute_mapping_is_canonical(self):
        event = self.event("event-1", 1, attributes={"z": 2, "a": "value"})
        self.assertEqual(event.attributes, (("a", "value"), ("z", 2)))

    def test_snapshot_round_trip(self):
        events = (
            self.event("event-2", 2, participants=("actor",), attributes={"ok": True}),
            self.event("event-1", 1, witnesses=("observer",)),
        )
        original = WorldEventLedger(events)
        restored = WorldEventLedger.from_snapshot(original.snapshot())
        self.assertEqual(restored.snapshot(), original.snapshot())

    def test_validation_rejects_mutable_or_non_finite_attributes(self):
        with self.assertRaises(ValueError):
            WorldEvent("event", 1, "incident", attributes=(("bad", float("nan")),))
        with self.assertRaises(ValueError):
            WorldEvent("event", 1, "incident", attributes=(("z", 1), ("a", 2)))

    def test_query_rejects_reversed_range(self):
        ledger = WorldEventLedger()
        with self.assertRaises(ValueError):
            ledger.query(start_tick=4, end_tick=2)


if __name__ == "__main__":
    unittest.main()
