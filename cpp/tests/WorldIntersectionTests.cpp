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
    return 0;
}
