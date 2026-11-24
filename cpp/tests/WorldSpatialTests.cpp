#include "simreality/SimulationWorld.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

using namespace simreality;

int main() {
    WorldState state;
    NPC forward;
    forward.entity_id = "forward-observer";
    NPC rear;
    rear.entity_id = "rear-observer";
    NPC blocked;
    blocked.entity_id = "blocked-observer";
    NPC actor;
    actor.entity_id = "actor";
    NPC unregistered;
    unregistered.entity_id = "unregistered";
    state.npcs = {forward, rear, blocked, actor, unregistered};
    SimulationWorld world(std::move(state));

    world.set_npc_spatial_state("forward-observer", {0.0, 0.0, 0.0},
                                {1.0, 0.0, 0.0});
    world.set_npc_spatial_state("rear-observer", {8.0, 0.0, 0.0},
                                {1.0, 0.0, 0.0});
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

    const auto audible = world.audible_npcs(
        {0.0, 0.0, 0.0}, 100.0, 10.0, 1.0,
        {{"blocked-observer", 0.01}});
    assert(audible.size() == 2U);
    assert(audible[0] == "forward-observer");
    assert(audible[1] == "rear-observer");

    bool rejected_invalid_sound_without_candidates = false;
    try {
        (void)world.audible_npcs({1000.0, 1000.0, 1000.0}, -1.0, 1.0, 0.0);
    } catch (const std::invalid_argument&) {
        rejected_invalid_sound_without_candidates = true;
    }
    assert(rejected_invalid_sound_without_candidates);

    world.set_npc_spatial_state("actor", {5.0, 0.0, 0.0},
                                {-1.0, 0.0, 0.0});
    Description witnessed_description;
    witnessed_description.height_m = 1.8;
    assert(world.record_spatially_witnessed_action(
        "actor", ActionTag::CrimeTheft, witnessed_description, 10.0,
        3.14159265358979323846, {"blocked-observer"}) == 1U);
    assert(world.state().npcs[0].memories.size() == 1U);
    assert(world.state().npcs[0].memories[0].target_entity_id == "actor");
    assert(world.state().npcs[2].memories.empty());
    assert(world.state().ongoing_events.size() == 1U);
    assert(world.state().ongoing_events[0].witness_ids.size() == 1U);
    assert(world.state().ongoing_events[0].witness_ids[0] == "forward-observer");

    const std::vector<SpatialPoint> straight_lane{
        {0.0, 0.0, 0.0}, {100.0, 0.0, 0.0}};
    const auto first_motion = world.advance_npc_on_lane(
        "forward-observer", straight_lane, 1.0, 2.0, 3.0, 10.0);
    assert(std::abs(first_motion.target.x - 2.0) < 1e-9);
    assert(world.nearby_npcs({3.0, 0.0, 0.0}, 0.01).size() == 1U);
    assert(world.nearby_npcs({3.0, 0.0, 0.0}, 0.01)[0] == "forward-observer");
    (void)world.advance_npc_on_lane(
        "forward-observer", straight_lane, 1.0, 2.0, 3.0, 10.0);
    assert(world.nearby_npcs({6.0, 0.0, 0.0}, 0.01).size() == 1U);

    // Predictive avoidance is integrated into the world movement step.
    world.set_npc_spatial_state("actor", {6.0, -1.0, 0.0}, {0.0, 1.0, 0.0},
                                {0.0, 2.0, 0.0});
    world.set_npc_spatial_state("blocked-observer", {50.0, 30.0, 0.0},
                                {0.0, -1.0, 0.0}, {0.0, -2.0, 0.0});
    const auto collision_aware = world.advance_npc_on_lane_avoiding_collisions(
        "forward-observer", straight_lane, 0.25, 2.0, 3.0, 10.0,
        0.5, 0.5, 3.0, 4.0, 10.0);
    (void)collision_aware;
    const auto collision_aware_position = world.nearby_npcs({6.75, 0.0, 0.0}, 0.5);
    assert(std::find(collision_aware_position.begin(), collision_aware_position.end(),
        "forward-observer") != collision_aware_position.end());

    world.configure_traffic_lane("main-road", 1U);
    world.advance_traffic_tick(1U);
    const auto traffic = world.resolve_lane_traffic({
        {"main-road", "forward-observer", 0},
        {"main-road", "actor", 0}});
    assert((traffic.granted_entity_ids == std::vector<std::string>{"actor"}));
    assert((traffic.denied_entity_ids == std::vector<std::string>{"forward-observer"}));
    bool movement_denied_without_reservation = false;
    try {
        (void)world.advance_npc_on_reserved_lane(
            "forward-observer", "main-road", straight_lane, 1.0, 2.0, 3.0, 10.0);
    } catch (const std::logic_error&) {
        movement_denied_without_reservation = true;
    }
    assert(movement_denied_without_reservation);
    (void)world.advance_npc_on_reserved_lane(
        "actor", "main-road", straight_lane, 1.0, 2.0, 3.0, 10.0);
    assert(world.release_lane_reservation("main-road", "actor"));
    world.advance_traffic_tick(2U);
    const auto next_traffic = world.resolve_lane_traffic({
        {"main-road", "forward-observer", 0}});
    assert((next_traffic.granted_entity_ids == std::vector<std::string>{"forward-observer"}));
    (void)world.advance_npc_on_reserved_lane(
        "forward-observer", "main-road", straight_lane, 1.0, 2.0, 3.0, 10.0);

    bool rejected_unregistered_actor = false;
    try {
        (void)world.record_spatially_witnessed_action(
            "unregistered", ActionTag::CrimeTheft, witnessed_description,
            10.0, 3.14159265358979323846);
    } catch (const std::logic_error&) {
        rejected_unregistered_actor = true;
    }
    assert(rejected_unregistered_actor);

    bool rejected_unknown_npc = false;
    try {
        world.set_npc_spatial_state("missing", {0.0, 0.0, 0.0},
                                    {1.0, 0.0, 0.0});
    } catch (const std::out_of_range&) {
        rejected_unknown_npc = true;
    }
    assert(rejected_unknown_npc);

    bool rejected_invalid_fov_without_candidates = false;
    try {
        (void)world.visible_npcs({1000.0, 1000.0, 1000.0}, 1.0, 7.0);
    } catch (const std::invalid_argument&) {
        rejected_invalid_fov_without_candidates = true;
    }
    assert(rejected_invalid_fov_without_candidates);

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
