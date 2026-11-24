#pragma once

#include "simreality/IntersectionTraffic.h"
#include "simreality/LaneTraffic.h"

#include <cstddef>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace simreality {

struct RouteEdgeDefinition {
    std::string source_lane_id{};
    std::string destination_lane_id{};
    std::string intersection_id{};
    std::string movement_id{};
    double traversal_cost{1.0};
    double congestion_cost_per_occupant{0.0};
    double hazard_penalty{0.0};
    double conflict_pressure_cost_per_reservation{0.0};
};

struct RouteStep {
    std::string lane_id{};
    std::string entry_intersection_id{};
    std::string entry_movement_id{};
};

struct RoutePlan {
    std::string source_lane_id{};
    std::string destination_lane_id{};
    std::vector<RouteStep> steps{};
    double total_cost{0.0};
};

struct RouteLookaheadIntents {
    std::vector<LaneTrafficRequest> lane_requests{};
    std::vector<IntersectionTrafficRequest> intersection_requests{};
};

// Deterministic directed-lane graph planner. Geometry and physical occupancy
// remain host-owned; congestion is supplied as a per-lane occupancy snapshot.
class TrafficRoutePlanner {
public:
    void upsert_edge(RouteEdgeDefinition edge);
    [[nodiscard]] bool erase_edge(
        const std::string& source_lane_id, const std::string& destination_lane_id);
    [[nodiscard]] RoutePlan plan(
        const std::string& source_lane_id,
        const std::string& destination_lane_id,
        const std::map<std::string, std::size_t>& lane_occupancy = {},
        const std::map<std::pair<std::string, std::string>, std::size_t>& conflict_pressure = {}) const;
    [[nodiscard]] RoutePlan plan_live(
        const std::string& source_lane_id, const std::string& destination_lane_id,
        const LaneTrafficCoordinator& live_lanes) const;
    [[nodiscard]] RoutePlan plan_live(
        const std::string& source_lane_id, const std::string& destination_lane_id,
        const LaneTrafficCoordinator& live_lanes,
        const IntersectionTrafficCoordinator& live_intersections) const;
    [[nodiscard]] RouteLookaheadIntents reservation_lookahead(
        const RoutePlan& route, std::size_t current_step_index,
        const std::string& entity_id, std::int32_t priority,
        std::size_t lookahead_segments = 1U) const;
    [[nodiscard]] std::size_t edge_count() const noexcept { return edges_.size(); }

private:
    struct EdgeKey {
        std::string source{};
        std::string destination{};
        [[nodiscard]] bool operator<(const EdgeKey& other) const noexcept;
    };
    std::map<EdgeKey, RouteEdgeDefinition> edges_{};
};

enum class RouteRecoveryAction {
    None,
    ReplanRequested
};

struct RouteProgressCheckpoint { std::string entity_id{}; std::uint64_t last_tick{0}; double last_progress{0.0}; std::uint64_t stalled_ticks{0}; };

struct RouteProgressObservation {
    std::string entity_id{};
    std::uint64_t tick{0};
    double progress{0.0};
    std::uint64_t stalled_ticks{0};
    RouteRecoveryAction action{RouteRecoveryAction::None};
};

// Tracks monotonic progress observations. A recovery signal never releases
// lane/intersection reservations or moves an entity; the host must acquire a
// replacement route's look-ahead grants before invoking the safe handoff.
class RouteProgressMonitor {
public:
    explicit RouteProgressMonitor(std::uint64_t stalled_tick_threshold = 3U);
    [[nodiscard]] RouteProgressObservation observe(
        const std::string& entity_id, std::uint64_t tick, double progress);
    [[nodiscard]] bool forget(const std::string& entity_id);
    [[nodiscard]] std::vector<RouteProgressCheckpoint> snapshot() const;
    void restore(const std::vector<RouteProgressCheckpoint>& snapshot);
    [[nodiscard]] std::uint64_t stalled_tick_threshold() const noexcept {
        return stalled_tick_threshold_;
    }

private:
    struct ProgressState {
        std::uint64_t last_tick{0};
        double last_progress{0.0};
        std::uint64_t stalled_ticks{0};
    };
    std::uint64_t stalled_tick_threshold_{3U};
    std::map<std::string, ProgressState> progress_{};
};

} // namespace simreality
