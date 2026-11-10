import unittest

from simreality.presence import PresenceLedger
from simreality.presence_witnesses import PresenceWitnessAdapter
from simreality.world_events import WorldEventLedger


class PresenceWitnessTests(unittest.TestCase):
    def test_only_present_candidates_with_explicit_opportunity_are_eligible(self):
        presence = PresenceLedger()
        presence.place("nearby", "market", 2)
        presence.place("elsewhere", "home", 2)
        presence.place("traveller", "market", 2)
        presence._records["traveller"] = presence.get("traveller").__class__(
            "traveller", "travelling", "market", "journey", "road", 0.4, 2
        )
        event = WorldEventLedger.make_event(
            "incident-1", 3, "incident", attributes={"location_id": "market"}
        )
        result = PresenceWitnessAdapter(presence).resolve(
            event, ("nearby", "elsewhere", "traveller", "absent"),
            {"nearby": True, "elsewhere": True, "traveller": True},
        )
        self.assertEqual(result.eligible_witnesses, ("nearby",))
        self.assertEqual(
            tuple((x.witness_id, x.reason) for x in result.assessments),
            (("absent", "no_recorded_presence"),
             ("elsewhere", "at_different_location"),
             ("nearby", "eligible"),
             ("traveller", "not_at_location")),
        )

    def test_same_location_without_opportunity_is_not_a_witness(self):
        presence = PresenceLedger()
        presence.place("npc", "street", 1)
        event = WorldEventLedger.make_event(
            "incident-2", 2, "incident", attributes={"location_id": "street"}
        )
        result = PresenceWitnessAdapter(presence).resolve(event, ("npc",), {"npc": False})
        self.assertEqual(result.eligible_witnesses, ())
        self.assertEqual(result.assessments[0].reason, "no_observation_opportunity")

    def test_resolution_is_canonical_and_does_not_mutate_event(self):
        presence = PresenceLedger()
        presence.place("b", "street", 1)
        presence.place("a", "street", 1)
        event = WorldEventLedger.make_event(
            "incident-3", 2, "incident", witnesses=("already-recorded",),
            attributes={"location_id": "street"},
        )
        result = PresenceWitnessAdapter(presence).resolve(
            event, ("b", "a"), {"a": True, "b": True}
        )
        self.assertEqual(result.eligible_witnesses, ("a", "b"))
        self.assertEqual(event.witnesses, ("already-recorded",))

    def test_rejects_invalid_opportunity_and_location_inputs(self):
        presence = PresenceLedger()
        event = WorldEventLedger.make_event("incident-4", 1, "incident")
        with self.assertRaisesRegex(ValueError, "location"):
            PresenceWitnessAdapter(presence).resolve(event, (), {})
        event = WorldEventLedger.make_event(
            "incident-5", 1, "incident", attributes={"location_id": "street"}
        )
        with self.assertRaisesRegex(ValueError, "booleans"):
            PresenceWitnessAdapter(presence).resolve(event, ("npc",), {"npc": 1})


if __name__ == "__main__":
    unittest.main()
