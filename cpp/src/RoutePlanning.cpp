#include "simreality/RoutePlanning.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace simreality {

bool TrafficRoutePlanner::EdgeKey::operator<(const EdgeKey& other) const noexcept {
    return std::tie(source, destination) < std::tie(other.source, other.destination);
}

void TrafficRoutePlanner::upsert_edge(RouteEdgeDefinition edge) {
    if (edge.source_lane_id.empty() || edge.destination_lane_id.empty()
        || edge.source_lane_id == edge.destination_lane_id
        || !std::isfinite(edge.traversal_cost) || edge.traversal_cost < 0.0
        || !std::isfinite(edge.congestion_cost_per_occupant)
        || edge.congestion_cost_per_occupant < 0.0
        || !std::isfinite(edge.conflict_pressure_cost_per_reservation)
        || edge.conflict_pressure_cost_per_reservation < 0.0
        || !std::isfinite(edge.hazard_penalty) || edge.hazard_penalty < 0.0
        || (edge.intersection_id.empty() != edge.movement_id.empty())) {
        throw std::invalid_argument("route edge contains invalid identifiers or costs");
    }
    edges_[{edge.source_lane_id, edge.destination_lane_id}] = std::move(edge);
}

bool TrafficRoutePlanner::erase_edge(
    const std::string& source_lane_id, const std::string& destination_lane_id) {
    return edges_.erase({source_lane_id, destination_lane_id}) != 0U;
}

RoutePlan TrafficRoutePlanner::plan(
    const std::string& source_lane_id,
    const std::string& destination_lane_id,
    const std::map<std::string, std::size_t>& lane_occupancy,
    const std::map<std::pair<std::string, std::string>, std::size_t>& conflict_pressure) const {
    if (source_lane_id.empty() || destination_lane_id.empty()) {
        throw std::invalid_argument("route endpoints must not be empty");
    }
    for (const auto& [lane_id, occupancy] : lane_occupancy) {
        (void)occupancy;
        if (lane_id.empty()) throw std::invalid_argument("occupancy lane ID must not be empty");
    }

    RoutePlan result;
    result.source_lane_id = source_lane_id;
    result.destination_lane_id = destination_lane_id;
    if (source_lane_id == destination_lane_id) {
        result.steps.push_back({source_lane_id, {}, {}});
        return result;
    }

    struct Label {
        double cost{std::numeric_limits<double>::infinity()};
        std::vector<std::string> path{};
        bool reached{false};
        bool settled{false};
    };
    std::map<std::string, Label> labels;
    labels[source_lane_id] = {0.0, {source_lane_id}, true, false};

    while (true) {
        auto selected = labels.end();
        for (auto candidate = labels.begin(); candidate != labels.end(); ++candidate) {
            if (!candidate->second.reached || candidate->second.settled) continue;
            if (selected == labels.end()
                || candidate->second.cost < selected->second.cost
                || (candidate->second.cost == selected->second.cost
                    && candidate->second.path < selected->second.path)) {
                selected = candidate;
            }
        }
        if (selected == labels.end()) break;
        const std::string current = selected->first;
        selected->second.settled = true;
        if (current == destination_lane_id) break;

        for (const auto& [key, edge] : edges_) {
            if (key.source != current) continue;
            Label& next = labels[key.destination];
            if (next.settled) continue;
            const auto occupancy = lane_occupancy.find(key.destination);
            const double occupied = occupancy == lane_occupancy.end()
                ? 0.0 : static_cast<double>(occupancy->second);
            const auto pressure = conflict_pressure.find({edge.intersection_id, edge.movement_id});
            const double conflicts = pressure == conflict_pressure.end()
                ? 0.0 : static_cast<double>(pressure->second);
            const double edge_cost = edge.traversal_cost
                + edge.hazard_penalty
                + edge.congestion_cost_per_occupant * occupied
                + edge.conflict_pressure_cost_per_reservation * conflicts;
            const double candidate_cost = selected->second.cost + edge_cost;
            if (!std::isfinite(candidate_cost)) {
                throw std::overflow_error("route cost is not representable");
            }
            std::vector<std::string> candidate_path = selected->second.path;
            if (std::find(candidate_path.begin(), candidate_path.end(), key.destination)
                != candidate_path.end()) {
                continue;
            }
            candidate_path.push_back(key.destination);
            if (!next.reached || candidate_cost < next.cost
                || (candidate_cost == next.cost && candidate_path < next.path)) {
                next.cost = candidate_cost;
                next.path = std::move(candidate_path);
                next.reached = true;
            }
        }
    }

    const auto destination = labels.find(destination_lane_id);
    if (destination == labels.end() || !destination->second.reached) {
        throw std::runtime_error("no directed route connects the requested lanes");
    }
    result.total_cost = destination->second.cost;
    result.steps.reserve(destination->second.path.size());
    result.steps.push_back({source_lane_id, {}, {}});
    for (std::size_t i = 1U; i < destination->second.path.size(); ++i) {
        const auto edge = edges_.find({
            destination->second.path[i - 1U], destination->second.path[i]});
        if (edge == edges_.end()) {
            throw std::logic_error("route reconstruction references a missing edge");
        }
        result.steps.push_back({
            edge->second.destination_lane_id,
            edge->second.intersection_id,
            edge->second.movement_id});
    }
    return result;
}

RoutePlan TrafficRoutePlanner::plan_live(
    const std::string& source_lane_id, const std::string& destination_lane_id,
    const LaneTrafficCoordinator& live_lanes) const {
    return plan(source_lane_id, destination_lane_id, live_lanes.occupancy_snapshot());
}

RoutePlan TrafficRoutePlanner::plan_live(
    const std::string& source_lane_id, const std::string& destination_lane_id,
    const LaneTrafficCoordinator& live_lanes,
    const IntersectionTrafficCoordinator& live_intersections) const {
    return plan(source_lane_id, destination_lane_id, live_lanes.occupancy_snapshot(),
        live_intersections.conflict_pressure_snapshot());
}

RouteLookaheadIntents TrafficRoutePlanner::reservation_lookahead(
    const RoutePlan& route, std::size_t current_step_index,
    const std::string& entity_id, std::int32_t priority,
    std::size_t lookahead_segments) const {
    if (entity_id.empty() || route.source_lane_id.empty()
        || route.destination_lane_id.empty() || route.steps.empty()
        || current_step_index >= route.steps.size() || lookahead_segments == 0U) {
        throw std::invalid_argument("route look-ahead arguments are invalid");
    }
    if (route.steps.front().lane_id.empty()
        || route.steps.front().lane_id != route.source_lane_id
        || route.steps.back().lane_id != route.destination_lane_id
        || !route.steps.front().entry_intersection_id.empty()
        || !route.steps.front().entry_movement_id.empty()) {
        throw std::invalid_argument("route plan endpoints or first step are inconsistent");
    }
    std::set<std::string> visited_lanes;
    for (const RouteStep& step : route.steps) {
        if (step.lane_id.empty() || !visited_lanes.insert(step.lane_id).second) {
            throw std::invalid_argument("route plan contains an empty or repeated lane");
        }
    }
    for (std::size_t i = 1U; i < route.steps.size(); ++i) {
        const RouteStep& previous = route.steps[i - 1U];
        const RouteStep& step = route.steps[i];
        if (step.entry_intersection_id.empty() != step.entry_movement_id.empty()) {
            throw std::invalid_argument("route plan contains an incomplete transition");
        }
        const auto edge = edges_.find({previous.lane_id, step.lane_id});
        if (edge == edges_.end()
            || edge->second.intersection_id != step.entry_intersection_id
            || edge->second.movement_id != step.entry_movement_id) {
            throw std::invalid_argument("route plan is stale or does not match this graph");
        }
    }

    RouteLookaheadIntents result;
    const std::size_t remaining = route.steps.size() - current_step_index - 1U;
    const std::size_t count = std::min(lookahead_segments, remaining);
    const std::size_t end = current_step_index + 1U + count;
    for (std::size_t i = current_step_index + 1U; i < end; ++i) {
        const RouteStep& step = route.steps[i];
        result.lane_requests.push_back({step.lane_id, entity_id, priority});
        if (!step.entry_intersection_id.empty()) {
            result.intersection_requests.push_back({
                step.entry_intersection_id, step.entry_movement_id, entity_id, priority});
        }
    }
    return result;
}

RouteProgressMonitor::RouteProgressMonitor(std::uint64_t stalled_tick_threshold)
    : stalled_tick_threshold_(stalled_tick_threshold) {
    if (stalled_tick_threshold_ == 0U) {
        throw std::invalid_argument("stalled tick threshold must be positive");
    }
}

RouteProgressObservation RouteProgressMonitor::observe(
    const std::string& entity_id, std::uint64_t tick, double progress) {
    if (entity_id.empty() || !std::isfinite(progress)) {
        throw std::invalid_argument("route progress observation is invalid");
    }
    auto found = progress_.find(entity_id);
    if (found == progress_.end()) {
        progress_.emplace(entity_id, ProgressState{tick, progress, 0U});
        return {entity_id, tick, progress, 0U, RouteRecoveryAction::None};
    }
    ProgressState& state = found->second;
    if (tick <= state.last_tick) {
        throw std::invalid_argument("route progress ticks must increase per entity");
    }
    if (progress > state.last_progress) {
        state.stalled_ticks = 0U;
        state.last_progress = progress;
    } else {
        const std::uint64_t elapsed_ticks = tick - state.last_tick;
        if (elapsed_ticks > std::numeric_limits<std::uint64_t>::max() - state.stalled_ticks) {
            state.stalled_ticks = std::numeric_limits<std::uint64_t>::max();
        } else {
            state.stalled_ticks += elapsed_ticks;
        }
    }
    state.last_tick = tick;
    const RouteRecoveryAction action = state.stalled_ticks >= stalled_tick_threshold_
        ? RouteRecoveryAction::ReplanRequested : RouteRecoveryAction::None;
    return {entity_id, tick, progress, state.stalled_ticks, action};
}

std::vector<RouteProgressCheckpoint> RouteProgressMonitor::snapshot() const {
    std::vector<RouteProgressCheckpoint> result;
    result.reserve(progress_.size());
    for (const auto& [entity_id, state] : progress_)
        result.push_back({entity_id, state.last_tick, state.last_progress, state.stalled_ticks});
    return result;
}

void RouteProgressMonitor::restore(const std::vector<RouteProgressCheckpoint>& value) {
    std::map<std::string, ProgressState> restored;
    for (const auto& item : value) {
        if (item.entity_id.empty() || !std::isfinite(item.last_progress)
            || !restored.emplace(item.entity_id,
                ProgressState{item.last_tick, item.last_progress, item.stalled_ticks}).second) {
            throw std::invalid_argument("invalid or duplicate route progress checkpoint");
        }
    }
    progress_ = std::move(restored);
}

bool RouteProgressMonitor::forget(const std::string& entity_id) {
    return progress_.erase(entity_id) != 0U;
}

} // namespace simreality
