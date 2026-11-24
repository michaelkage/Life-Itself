import unittest

from simreality.model import NPC
from simreality.presence import PresenceLedger, PresenceTickAdapter
from simreality.route_planning import PersonalRoutePlanner, RouteEdge
from simreality.population_execution import PopulationExecutionLoop, PresenceEncounterIntent
from simreality.presence_encounters import PresenceSocialAdapter, PresenceEncounterLedger
from simreality.routine_execution import RoutineExecutionLedger
from simreality.routines import RoutineBook
from simreality.simulation_tick import SimulationTickCoordinator
from simreality.social_beliefs import SocialBeliefSystem
from simreality.social_conversations import SocialConversationAdapter
from simreality.social_trust import SocialTrustLedger
from simreality.travel import TravelTickAdapter
from simreality.world_event_memory import WorldEventMemoryAdapter
from simreality.world_events import WorldEventLedger


class PopulationTravelIntegrationTests(unittest.TestCase):
    def test_travel_advances_before_presence_is_synchronized_in_population_tick(self):
        events = WorldEventLedger()
        trust = SocialTrustLedger()
        conversations = SocialConversationAdapter(trust, SocialBeliefSystem(trust))
        coordinator = SimulationTickCoordinator(events, WorldEventMemoryAdapter(events), conversations)
        edges = (RouteEdge("road", "home", "office", 3),)
        planner = PersonalRoutePlanner(edges)
        travel = TravelTickAdapter(edges)
        travel.start("trip-a", "npc-a", planner.plan("npc-a", "home", "office"), 0)
        presence = PresenceLedger()
        presence.place("npc-a", "home", 0)
        loop = PopulationExecutionLoop(
            coordinator, RoutineBook(), RoutineExecutionLedger(),
            travel_adapter=travel, presence_adapter=PresenceTickAdapter(presence),
        )
        result = loop.run_tick(
            1, 0, {"npc-a": NPC("npc-a")}, outcome_samples={},
            travel_budgets={"npc-a": 2.0},
        )
        self.assertEqual(result.travel.journeys[0].edge_progress, 2.0)
        self.assertEqual(result.presence[0].status, "travelling")
        self.assertEqual(result.presence[0].edge_id, "road")
        self.assertEqual(events.query(event_type="npc_presence_updated")[0].tick, 1)

    def test_travel_budget_is_required_when_travel_is_configured(self):
        events = WorldEventLedger()
        trust = SocialTrustLedger()
        conversations = SocialConversationAdapter(trust, SocialBeliefSystem(trust))
        coordinator = SimulationTickCoordinator(events, WorldEventMemoryAdapter(events), conversations)
        edges = (RouteEdge("road", "home", "office", 3),)
        travel = TravelTickAdapter(edges)
        loop = PopulationExecutionLoop(
            coordinator, RoutineBook(), RoutineExecutionLedger(),
            travel_adapter=travel, presence_adapter=PresenceTickAdapter(PresenceLedger()),
        )
        with self.assertRaisesRegex(ValueError, "travel_budgets are required"):
            loop.run_tick(1, 0, {"npc-a": NPC("npc-a")}, outcome_samples={})
        self.assertEqual(coordinator.snapshot(), ())


    def test_explicit_encounter_opportunity_is_materialized_and_processed_in_same_tick(self):
        events = WorldEventLedger()
        trust = SocialTrustLedger()
        conversations = SocialConversationAdapter(trust, SocialBeliefSystem(trust))
        coordinator = SimulationTickCoordinator(events, WorldEventMemoryAdapter(events), conversations)
        edges = (RouteEdge("road-a", "home-a", "market", 1), RouteEdge("road-b", "home-b", "market", 1))
        planner = PersonalRoutePlanner(edges)
        travel = TravelTickAdapter(edges)
        travel.start("trip-a", "npc-a", planner.plan("npc-a", "home-a", "market"), 0)
        travel.start("trip-b", "npc-b", planner.plan("npc-b", "home-b", "market"), 0)
        presence = PresenceLedger()
        presence.place("npc-a", "home-a", 0)
        presence.place("npc-b", "home-b", 0)
        presence_adapter = PresenceTickAdapter(presence)
        encounter_adapter = PresenceSocialAdapter(presence, PresenceEncounterLedger())
        loop = PopulationExecutionLoop(
            coordinator, RoutineBook(), RoutineExecutionLedger(),
            travel_adapter=travel, presence_adapter=presence_adapter,
            encounter_adapter=encounter_adapter,
        )
        result = loop.run_tick(
            1, 0, {"npc-a": NPC("npc-a"), "npc-b": NPC("npc-b")},
            outcome_samples={}, travel_budgets={"npc-a": 1, "npc-b": 1},
            encounter_opportunities=(PresenceEncounterIntent("meet-a-b", "npc-a", "npc-b"),),
        )
        self.assertEqual(len(result.encounters), 1)
        self.assertEqual(result.encounters[0].encounter.location_id, "market")
        self.assertEqual(events.query(event_type="npc_encounter")[0].participants, ("npc-a", "npc-b"))
        self.assertEqual(events.query(event_type="npc_encounter")[0].witnesses, ("npc-a", "npc-b"))


if __name__ == "__main__":
    unittest.main()
