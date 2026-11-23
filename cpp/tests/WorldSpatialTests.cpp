#include "simreality/SimulationWorld.h"

#include <cassert>
#include <cmath>
#include <set>
#include <stdexcept>
#include <utility>

using namespace simreality;

int main() {
    WorldState state;
    NPC forward;
    forward.entity_id = "forward-observer";
    NPC rear;
    rear.entity_id = "rear-observer";
    NPC blocked;
    blocked.entity_id = "blocked-observer";
    state.npcs = {forward, rear, blocked};
    SimulationWorld world(std::move(state));

    world.set_npc_spatial_state("forward-observer", {0.0, 0.0, 0.0},
                                {1.0, 0.0, 0.0});
    world.set_npc_spatial_state("rear-observer", {8.0, 0.0, 0.0},
                                {-1.0, 0.0, 0.0});
    world.set_npc_spatial_state("blocked-observer", {4.0, 1.0, 0.0},
                                {1.0, 0.0, 0.0});

    const auto nearby = world.nearby_npcs({0.0, 0.0, 0.0}, 5.0);
    assert(nearby.size() == 2U);
    assert(nearby[0] == "blocked-observer");
    assert(nearby[1] == "forward-observer");

    const auto visible = world.visible_npcs({5.0, 0.0, 0.0}, 10.0,
        3.14159265358979323846);
    assert(visible.size() == 2U);
    assert(visible[0] == "blocked-observer");
    assert(visible[1] == "forward-observer");

    const auto occluded = world.visible_npcs({5.0, 0.0, 0.0}, 10.0,
        3.14159265358979323846, {"blocked-observer"});
    assert(occluded.size() == 1U);
    assert(occluded[0] == "forward-observer");

    bool rejected_unknown_npc = false;
    try {
        world.set_npc_spatial_state("missing", {0.0, 0.0, 0.0},
                                    {1.0, 0.0, 0.0});
    } catch (const std::out_of_range&) {
        rejected_unknown_npc = true;
    }
    assert(rejected_unknown_npc);

    bool rejected_zero_forward = false;
    try {
        world.set_npc_spatial_state("forward-observer", {0.0, 0.0, 0.0}, {});
    } catch (const std::invalid_argument&) {
        rejected_zero_forward = true;
    }
    assert(rejected_zero_forward);

    assert(world.remove_npc_spatial_state("rear-observer"));
    assert(!world.remove_npc_spatial_state("rear-observer"));
    const auto remaining = world.nearby_npcs({8.0, 0.0, 0.0}, 0.0);
    assert(remaining.empty());
    return 0;
}
