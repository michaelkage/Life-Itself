#include "simreality/Spatial.h"

#include <cassert>
#include <cmath>
#include <stdexcept>
#include <vector>

using namespace simreality;

int main() {
    const std::vector<SpatialPoint> lane{
        {0.0, 0.0, 0.0}, {10.0, 0.0, 0.0}, {10.0, 10.0, 0.0}};
    const auto result = compute_lane_following(
        {4.0, 2.0, 0.0}, {1.0, 0.0, 0.0}, lane, 3.0, 5.0, 2.0);
    assert(std::abs(result.nearest_distance - 2.0) < 1e-9);
    assert(result.segment_index == 0U);
    assert(std::abs(result.lane_progress - 4.0) < 1e-9);
    assert(std::abs(result.target.x - 7.0) < 1e-9);
    assert(std::abs(result.target.y) < 1e-9);
    assert(std::abs(std::hypot(result.steering_force.x,
                               result.steering_force.y,
                               result.steering_force.z) - 2.0) < 1e-9);

    const auto corner = compute_lane_following(
        {10.0, 1.0, 0.0}, {0.0, 1.0, 0.0}, lane, 2.0, 4.0, 10.0);
    assert(corner.segment_index == 1U);
    assert(std::abs(corner.target.x - 10.0) < 1e-9);
    assert(std::abs(corner.target.y - 3.0) < 1e-9);

    const auto clamped = compute_lane_following(
        {10.0, 9.0, 0.0}, {}, lane, 20.0, 3.0, 1.0);
    assert(std::abs(clamped.target.x - 10.0) < 1e-9);
    assert(std::abs(clamped.target.y - 10.0) < 1e-9);
    assert(std::abs(std::hypot(clamped.steering_force.x,
                               clamped.steering_force.y,
                               clamped.steering_force.z) - 1.0) < 1e-9);

    const auto stationary = compute_lane_following(
        {5.0, 0.0, 0.0}, {}, lane, 0.0, 0.0, 0.0);
    assert(stationary.desired_velocity.x == 0.0);
    assert(stationary.steering_force.x == 0.0);

    const std::vector<MovingBody> crossing{
        {"pedestrian-b", {5.0, -5.0, 0.0}, {0.0, 2.0, 0.0}, 0.5},
        {"vehicle-a", {5.0, 3.0, 0.0}, {0.0, -2.0, 0.0}, 1.0}};
    const auto avoidance = compute_collision_avoidance(
        "subject", {0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, 0.5,
        crossing, 3.0, 4.0);
    assert(avoidance.predicted_conflicts == 2U);
    assert(avoidance.magnitude > 0.0 && avoidance.magnitude <= 4.0);
    assert(avoidance.earliest_conflict_seconds > 0.0);
    const auto reordered = compute_collision_avoidance(
        "subject", {0.0, 0.0, 0.0}, {2.0, 0.0, 0.0}, 0.5,
        {crossing[1], crossing[0]}, 3.0, 4.0);
    assert(avoidance.acceleration.x == reordered.acceleration.x);
    assert(avoidance.acceleration.y == reordered.acceleration.y);
    assert(avoidance.acceleration.z == reordered.acceleration.z);

    const auto separated = compute_collision_avoidance(
        "subject", {0.0, 0.0, 0.0}, {}, 0.5,
        {{"far", {10.0, 0.0, 0.0}, {}, 0.5}}, 2.0, 3.0);
    assert(separated.predicted_conflicts == 0U);
    assert(separated.magnitude == 0.0);

    const auto overlap = compute_collision_avoidance(
        "subject", {}, {}, 0.5,
        {{"coincident", {}, {}, 0.5}}, 1.0, 2.0);
    assert(overlap.predicted_conflicts == 1U);
    assert(std::abs(overlap.magnitude - 1.0) < 1e-9);

    bool rejected_duplicate_body = false;
    try {
        (void)compute_collision_avoidance("subject", {}, {}, 0.5,
            {{"same", {}, {}, 0.5}, {"same", {}, {}, 0.5}}, 1.0, 1.0);
    } catch (const std::invalid_argument&) {
        rejected_duplicate_body = true;
    }
    assert(rejected_duplicate_body);

    bool rejected_degenerate_lane = false;
    try {
        (void)compute_lane_following({0.0, 0.0, 0.0}, {}, {{1.0, 1.0, 1.0},
            {1.0, 1.0, 1.0}}, 1.0, 1.0, 1.0);
    } catch (const std::invalid_argument&) {
        rejected_degenerate_lane = true;
    }
    assert(rejected_degenerate_lane);

    bool rejected_nan = false;
    try {
        (void)compute_lane_following({0.0, 0.0, 0.0}, {},
            lane, std::nan(""), 1.0, 1.0);
    } catch (const std::invalid_argument&) {
        rejected_nan = true;
    }
    assert(rejected_nan);
    return 0;
}
