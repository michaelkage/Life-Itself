#pragma once

#include "simreality/IntersectionTraffic.h"
#include "simreality/LaneTraffic.h"

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace simreality {

struct JourneyOccupancy {
    std::string entity_id{};
    std::string lane_id{};
    std::string intersection_id{};
    std::string movement_id{};
};

struct JourneyRenewalResult {
    LaneTrafficResolution lanes{};
    IntersectionTrafficResolution intersections{};
};

// Renews only explicitly tracked physical occupancy. Removing an entity from
// this manager never releases a coordinator token; callers must first observe
// physical clearance and explicitly release through the owning coordinator.
class JourneyReservationManager {
public:
    void track(JourneyOccupancy occupancy);
    [[nodiscard]] bool forget_after_clearance(const std::string& entity_id);
    [[nodiscard]] JourneyRenewalResult advance_and_renew(
        std::uint64_t tick, LaneTrafficCoordinator& lanes,
        IntersectionTrafficCoordinator& intersections);
    [[nodiscard]] const std::map<std::string, JourneyOccupancy>& tracked() const noexcept {
        return tracked_;
    }

private:
    std::map<std::string, JourneyOccupancy> tracked_{};
};

struct WaitForEdge {
    std::string waiter_id{};
    std::string blocker_id{};
};

// Reports canonical strongly connected components in the wait-for graph.
// A component is a deadlock candidate, not permission to revoke occupancy.
class TrafficDeadlockDetector {
public:
    [[nodiscard]] std::vector<std::vector<std::string>> detect(
        const std::vector<WaitForEdge>& edges) const;
};

} // namespace simreality
