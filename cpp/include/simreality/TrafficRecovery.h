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
    [[nodiscard]] std::vector<JourneyOccupancy> snapshot() const;
    void restore(const std::vector<JourneyOccupancy>& snapshot);
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

enum class BlockedResourceKind { Lane, Intersection };
struct WaitForResourceEdge {
    std::string waiter_id{};
    std::string blocker_id{};
    BlockedResourceKind resource_kind{BlockedResourceKind::Lane};
    std::string resource_id{};
};
struct DeadlockResource {
    BlockedResourceKind kind{BlockedResourceKind::Lane};
    std::string resource_id{};
    std::string current_owner_id{};
};
struct DeadlockResolutionProposal {
    std::vector<std::string> participants{};
    std::string yielding_entity_id{};
    std::vector<DeadlockResource> blocking_resources{};
    std::vector<LaneTrafficRequest> replacement_lane_requests{};
    std::vector<IntersectionTrafficRequest> replacement_intersection_requests{};
};

// Reports canonical strongly connected components in the wait-for graph.
// A component is a deadlock candidate, not permission to revoke occupancy.
struct TrafficRecoveryCheckpoint {
    LaneTrafficSnapshot lanes{};
    IntersectionTrafficSnapshot intersections{};
    std::vector<JourneyOccupancy> journey_occupancy{};
    std::uint64_t progress_stall_threshold{3U};
    std::vector<RouteProgressCheckpoint> route_progress{};
    std::vector<WaitForResourceEdge> pending_wait_edges{};
};

class TrafficDeadlockDetector {
public:
    [[nodiscard]] std::vector<std::vector<std::string>> detect(
        const std::vector<WaitForEdge>& edges) const;
    [[nodiscard]] std::vector<DeadlockResolutionProposal> propose_resolutions(
        const std::vector<WaitForResourceEdge>& edges,
        const std::map<std::string, std::pair<std::vector<LaneTrafficRequest>,
            std::vector<IntersectionTrafficRequest>>>& replacement_reservations) const;
};

} // namespace simreality
