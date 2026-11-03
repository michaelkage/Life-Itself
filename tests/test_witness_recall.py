import unittest

from simreality.world_events import WorldEventLedger
from simreality.witness_recall import (
    RecallDetail, WitnessRecallAdapter, WitnessRecallProfile,
)


class WitnessRecallTests(unittest.TestCase):
    def setUp(self):
        self.events = WorldEventLedger()
        self.events.append(WorldEventLedger.make_event(
            "incident-1", 12, "street_incident", witnesses=("w1", "w2"),
            attributes={"sound": "glass_break", "clothing": "blue_coat", "location": "market"},
        ))
        self.details = (
            RecallDetail("d-clothing", "clothing", "visual", 0.8),
            RecallDetail("d-location", "location", "spatial", 0.7),
            RecallDetail("d-sound", "sound", "auditory", 0.9),
        )
        self.samples = {"d-clothing": 0.2, "d-location": 0.4, "d-sound": 0.3}

    def test_attention_profiles_recall_different_details(self):
        adapter = WitnessRecallAdapter(self.events)
        visual = WitnessRecallProfile("w1", (("auditory", 0.2), ("spatial", 0.4), ("visual", 1.5)))
        auditory = WitnessRecallProfile("w2", (("auditory", 1.5), ("spatial", 0.2), ("visual", 0.2)))
        r1 = adapter.recall("incident-1", visual, self.details, self.samples)
        r2 = adapter.recall("incident-1", auditory, self.details, self.samples)
        self.assertEqual([d.detail_id for d in r1.details], ["d-clothing"])
        self.assertEqual([d.detail_id for d in r2.details], ["d-sound"])
        self.assertEqual(dict((d.detail_id, d.value) for d in r1.details)["d-clothing"], "blue_coat")

    def test_replay_is_idempotent_and_conflicting_samples_rejected(self):
        adapter = WitnessRecallAdapter(self.events)
        profile = WitnessRecallProfile("w1")
        first = adapter.recall("incident-1", profile, self.details, self.samples)
        second = adapter.recall("incident-1", profile, self.details, self.samples)
        self.assertIs(first, second)
        changed = dict(self.samples, **{"d-sound": 0.1})
        with self.assertRaises(ValueError):
            adapter.recall("incident-1", profile, self.details, changed)

    def test_only_recorded_witnesses_can_recall(self):
        adapter = WitnessRecallAdapter(self.events)
        with self.assertRaises(ValueError):
            adapter.recall("incident-1", WitnessRecallProfile("stranger"), self.details, self.samples)

    def test_missing_attributes_and_bad_samples_rejected(self):
        adapter = WitnessRecallAdapter(self.events)
        with self.assertRaises(ValueError):
            adapter.recall("incident-1", WitnessRecallProfile("w1"),
                          (RecallDetail("x", "missing", "visual"),), {"x": 0.2})
        with self.assertRaises(ValueError):
            adapter.recall("incident-1", WitnessRecallProfile("w1"), self.details,
                          dict(self.samples, **{"d-sound": 1.2}))


if __name__ == "__main__":
    unittest.main()
