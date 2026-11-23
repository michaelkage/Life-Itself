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
