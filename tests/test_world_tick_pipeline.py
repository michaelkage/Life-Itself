import unittest

from simreality.model import NPC
from simreality.presence import PresenceLedger, PresenceTickAdapter
from simreality.presence_encounters import PresenceSocialAdapter
from simreality.route_planning import PersonalRoutePlanner, RouteEdge
from simreality.simulation_tick import SimulationTickCoordinator
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger
from simreality.travel import TravelTickAdapter
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger
from simreality.world_tick_pipeline import (
    PresenceEncounterIntent,
    SimulationWorldTickPipeline,
)


class WorldTickPipelineTests(unittest.TestCase):
    def make_pipeline(self):
        events = WorldEventLedger()
        trust = SocialTrustLedger()
        beliefs = SocialBeliefSystem(trust)
        conversations = SocialConversationAdapter(trust, beliefs)
        memory = WorldEventMemoryAdapter(events)
        coordinator = SimulationTickCoordinator(events, memory, conversations)

        edges = (RouteEdge("home-market", "home", "market", 2.0),)
        planner = PersonalRoutePlanner(edges)
        travel = TravelTickAdapter(edges)
        travel.start("journey-a", "a", planner.plan("a", "home", "market"), 0)

        presence_ledger = PresenceLedger()
        presence_ledger.place("a", "home", 0)
        presence_ledger.place("b", "market", 0)
        presence_ledger.place("c", "market", 0)
        presence = PresenceTickAdapter(presence_ledger)
        encounters = PresenceSocialAdapter(presence_ledger)
        pipeline = SimulationWorldTickPipeline(coordinator, travel, presence, encounters)
        npcs = {key: NPC(key) for key in ("a", "b", "c")}
        return pipeline, planner, npcs, events, travel, presence_ledger, encounters

    def test_tick_orders_travel_presence_then_confirmed_encounters(self):
        pipeline, planner, npcs, events, travel, presence, encounters = self.make_pipeline()
        result = pipeline.step(
            1, npcs, travel_budgets={"a": 2.0},
            encounter_intents=(PresenceEncounterIntent("meet-bc", "b", "c"),),
        )
        self.assertEqual(result.travel.arrivals, ("journey-a",))
        self.assertEqual(presence.get("a").status, "at_location")
        self.assertEqual(presence.get("a").location_id, "market")
        self.assertEqual(len(result.encounters), 1)
        self.assertEqual(result.encounters[0].encounter.participants, ("b", "c"))
        self.assertEqual(events.get("travel-arrival:journey-a").event_type, "npc_arrived")
        self.assertEqual(events.get("npc_encounter:meet-bc").event_type, "npc_encounter")

    def test_identical_replay_returns_cached_atomic_result(self):
        pipeline, _, npcs, _, _, _, _ = self.make_pipeline()
        kwargs = {"travel_budgets": {"a": 0.5}}
        first = pipeline.step(1, npcs, **kwargs)
        second = pipeline.step(1, npcs, **kwargs)
        self.assertIs(first, second)
        with self.assertRaisesRegex(ValueError, "different inputs"):
            pipeline.step(1, npcs, travel_budgets={"a": 1.0})

    def test_failure_rolls_back_all_prior_phases_and_allows_retry(self):
        pipeline, _, npcs, events, travel, presence, encounters = self.make_pipeline()
        with self.assertRaisesRegex(ValueError, "physically at a location"):
            pipeline.step(
                1, npcs, travel_budgets={"a": 0.75},
                encounter_intents=(PresenceEncounterIntent("invalid-meet", "a", "b"),),
            )
        self.assertEqual(travel.ledger.tick_snapshot(), ())
        self.assertEqual(presence.tick_snapshot(), ())
        self.assertEqual(encounters.ledger.tick_snapshot(), ())
        self.assertEqual(events.snapshot(), ())
        self.assertEqual(pipeline.coordinator.snapshot(), ())

        recovered = pipeline.step(1, npcs, travel_budgets={"a": 0.75})
        self.assertEqual(recovered.travel.journeys[0].edge_progress, 0.75)
        self.assertEqual(presence.get("a").status, "travelling")


    def test_social_phase_failure_rolls_back_travel_presence_and_events(self):
        pipeline, _, npcs, events, travel, presence, encounters = self.make_pipeline()
        with self.assertRaises(KeyError):
            pipeline.step(
                1, npcs, travel_budgets={"a": 0.5},
                event_ids=("missing-authoritative-event",),
            )
        self.assertEqual(travel.ledger.tick_snapshot(), ())
        self.assertEqual(presence.tick_snapshot(), ())
        self.assertEqual(encounters.ledger.tick_snapshot(), ())
        self.assertEqual(events.snapshot(), ())
        self.assertEqual(pipeline.coordinator.snapshot(), ())
        result = pipeline.step(1, npcs, travel_budgets={"a": 0.5})
        self.assertEqual(result.travel.journeys[0].edge_progress, 0.5)

    def test_unconfirmed_opportunity_does_not_create_encounter(self):
        pipeline, _, npcs, events, _, _, encounters = self.make_pipeline()
        result = pipeline.step(
            1, npcs, travel_budgets={"a": 0.0},
            encounter_intents=(PresenceEncounterIntent(
                "declined", "b", "c", opportunity=False
            ),),
        )
        self.assertEqual(result.encounters, ())
        self.assertIsNone(encounters.ledger.get("declined"))
        self.assertEqual(events.query(event_type="npc_encounter"), ())


if __name__ == "__main__":
    unittest.main()
