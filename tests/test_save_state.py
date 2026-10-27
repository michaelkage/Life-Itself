import unittest
from simreality.save_state import SimulationSaveEnvelope
from simreality.world_events import WorldEventLedger

class SaveStateTests(unittest.TestCase):
    def ledger(self):
        return WorldEventLedger((
            WorldEventLedger.make_event("b", 2, "talk", participants=("a", "b"), witnesses=("a",), attributes={"score": 0.75}),
            WorldEventLedger.make_event("a", 1, "arrival"),
        ))

    def test_round_trip_canonical(self):
        save = SimulationSaveEnvelope.capture(2, self.ledger(), metadata={"build": "dev", "seed": 42})
        payload = save.to_json()
        restored = SimulationSaveEnvelope.from_json(payload)
        self.assertEqual(restored, save)
        self.assertEqual(restored.to_json(), payload)

    def test_restore_ledger(self):
        save = SimulationSaveEnvelope.capture(2, self.ledger())
        self.assertEqual(SimulationSaveEnvelope.from_json(save.to_json()).restore_event_ledger().snapshot(), self.ledger().snapshot())

    def test_future_event_rejected(self):
        ledger = WorldEventLedger((WorldEventLedger.make_event("future", 3, "future"),))
        with self.assertRaises(ValueError):
            SimulationSaveEnvelope.capture(2, ledger)

    def test_bad_schema_rejected(self):
        with self.assertRaises(ValueError):
            SimulationSaveEnvelope.from_json('{"schema_version":99}')

    def test_bad_json_rejected(self):
        with self.assertRaises(ValueError):
            SimulationSaveEnvelope.from_json("{broken")

    def test_duplicate_metadata_rejected(self):
        with self.assertRaises(ValueError):
            SimulationSaveEnvelope(0, (), (("seed", 1), ("seed", 2)))

if __name__ == "__main__":
    unittest.main()
