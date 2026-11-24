#include "simreality/SimulationWorld.h"

#include <algorithm>
#include <cassert>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace simreality;

int main() {
    WorldState state;
    NPC first;
    first.entity_id = "npc-a";
    NPC second;
    second.entity_id = "npc-b";
    state.npcs = {first, second};
    SimulationWorld world(std::move(state));
    const std::vector<SpatialPoint> lane{{0.0, 0.0, 0.0}, {100.0, 0.0, 0.0}};
    world.set_npc_spatial_state("npc-a", {0.0, 0.0, 0.0}, {1.0, 0.0, 0.0});
    world.set_npc_spatial_state("npc-b", {0.0, 2.0, 0.0}, {1.0, 0.0, 0.0});

    world.configure_intersection_movement({"junction", "north-south", {"center", "south"}});
    world.configure_intersection_movement({"junction", "east-west", {"center", "west"}});
    world.configure_intersection_movement({"junction", "right-turn", {"north-corner"}});
    world.advance_intersection_tick(10U);
    const auto result = world.resolve_intersection_traffic({
        {"junction", "north-south", "npc-a", 0},
        {"junction", "east-west", "npc-b", 0}});
    assert((result.granted_entity_ids == std::vector<std::string>{"npc-a"}));
    assert((result.denied_entity_ids == std::vector<std::string>{"npc-b"}));

    bool denied = false;
    try {
        (void)world.advance_npc_on_reserved_intersection_movement(
            "npc-b", "junction", "east-west", lane, 1.0, 2.0, 3.0, 10.0);
    } catch (const std::logic_error&) {
        denied = true;
    }
    assert(denied);

    const auto moved = world.advance_npc_on_reserved_intersection_movement(
        "npc-a", "junction", "north-south", lane, 0.5, 2.0, 3.0, 10.0);
    (void)moved;
    const auto after_entry = world.nearby_npcs({0.0, 0.0, 0.0}, 100.0);
    assert(std::find(after_entry.begin(), after_entry.end(), "npc-a") != after_entry.end());
    assert(world.release_intersection_reservation("junction", "npc-a"));

    world.advance_intersection_tick(11U);
    const auto next = world.resolve_intersection_traffic({
        {"junction", "east-west", "npc-b", 0},
        {"junction", "right-turn", "npc-a", 0}});
    assert((next.granted_entity_ids == std::vector<std::string>{"npc-a", "npc-b"}));

    // Route handoff acquires the next lane and intersection before releasing
    // the old lane/intersection occupancy, and uses collision-aware movement.
    WorldState route_state;
    NPC traveler;
    traveler.entity_id = "traveler";
    NPC bystander;
    bystander.entity_id = "bystander";
    route_state.npcs = {traveler, bystander};
    SimulationWorld route_world(std::move(route_state));
    route_world.set_npc_spatial_state("traveler", {0.0, 0.0, 0.0}, {1.0, 0.0, 0.0});
    route_world.set_npc_spatial_state("bystander", {20.0, 20.0, 0.0}, {0.0, 1.0, 0.0});
    route_world.configure_traffic_lane("old-lane", 1U);
    route_world.configure_traffic_lane("new-lane", 1U);
    route_world.advance_traffic_tick(1U);
    assert((route_world.resolve_lane_traffic({
        {"old-lane", "traveler", 0}}).granted_entity_ids
        == std::vector<std::string>{"traveler"}));
    route_world.advance_traffic_tick(2U);
    assert((route_world.resolve_lane_traffic({
        {"new-lane", "traveler", 0}}).granted_entity_ids
        == std::vector<std::string>{"traveler"}));

    route_world.configure_intersection_movement({"previous-junction", "through", {"old-zone"}});
    route_world.configure_intersection_movement({"next-junction", "through", {"next-zone"}});
    route_world.advance_intersection_tick(1U);
    assert((route_world.resolve_intersection_traffic({
        {"previous-junction", "through", "traveler", 0}}).granted_entity_ids
        == std::vector<std::string>{"traveler"}));
    route_world.advance_intersection_tick(2U);
    assert((route_world.resolve_intersection_traffic({
        {"next-junction", "through", "traveler", 0}}).granted_entity_ids
        == std::vector<std::string>{"traveler"}));

    RouteSegmentRequest segment;
    segment.source_lane_id = "old-lane";
    segment.destination_lane_id = "new-lane";
    segment.entry_intersection_id = "next-junction";
    segment.entry_movement_id = "through";
    segment.cleared_intersection_id = "previous-junction";
    segment.cleared_movement_id = "through";
    segment.lane_centerline = {{0.0, 0.0, 0.0}, {100.0, 0.0, 0.0}};
    segment.elapsed_seconds = 0.25;
    segment.lookahead_distance = 2.0;
    segment.desired_speed = 3.0;
    segment.lane_maximum_acceleration = 10.0;
    segment.collision_radius = 0.5;
    segment.neighbor_collision_radius = 0.5;
    segment.prediction_horizon_seconds = 2.0;
    segment.maximum_avoidance_acceleration = 4.0;
    segment.broadphase_radius = 10.0;
    const auto handoff = route_world.advance_npc_on_reserved_route_segment(
        "traveler", segment);
    assert(handoff.source_lane_released);
    assert(handoff.cleared_intersection_released);
    assert(!route_world.release_lane_reservation("old-lane", "traveler"));
    assert(!route_world.release_intersection_reservation("previous-junction", "traveler"));
    assert(route_world.release_lane_reservation("new-lane", "traveler"));
    assert(route_world.release_intersection_reservation("next-junction", "traveler"));
    return 0;
}
