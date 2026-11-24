#include "simreality/TrafficRecovery.h"

#include <algorithm>
#include <functional>
#include <set>
#include <stdexcept>
#include <tuple>

namespace simreality {

void JourneyReservationManager::track(JourneyOccupancy occupancy) {
    if (occupancy.entity_id.empty() || occupancy.lane_id.empty()
        || (occupancy.intersection_id.empty() != occupancy.movement_id.empty())) {
        throw std::invalid_argument("journey occupancy identifiers are incomplete");
    }
    const auto found = tracked_.find(occupancy.entity_id);
    if (found != tracked_.end() && found->second.lane_id != occupancy.lane_id) {
        throw std::logic_error("journey lane changes require confirmed handoff before tracking");
    }
    tracked_[occupancy.entity_id] = std::move(occupancy);
}

bool JourneyReservationManager::forget_after_clearance(const std::string& entity_id) {
    return tracked_.erase(entity_id) != 0U;
}

JourneyRenewalResult JourneyReservationManager::advance_and_renew(
    std::uint64_t tick, LaneTrafficCoordinator& lanes,
    IntersectionTrafficCoordinator& intersections) {
    // Advance both clocks before constructing any renewal batch. The
    // coordinators expire leases first; resolve() then renews surviving grants.
    lanes.advance_tick(tick);
    intersections.advance_tick(tick);
    std::vector<LaneTrafficRequest> lane_requests;
    std::vector<IntersectionTrafficRequest> intersection_requests;
    lane_requests.reserve(tracked_.size());
    for (const auto& [entity_id, occupancy] : tracked_) {
        lane_requests.push_back({occupancy.lane_id, entity_id, 0});
        if (!occupancy.intersection_id.empty()) {
            intersection_requests.push_back({
                occupancy.intersection_id, occupancy.movement_id, entity_id, 0});
        }
    }
    JourneyRenewalResult result;
    result.lanes = lanes.resolve(lane_requests);
    result.intersections = intersections.resolve(intersection_requests);
    return result;
}

std::vector<std::vector<std::string>> TrafficDeadlockDetector::detect(
    const std::vector<WaitForEdge>& edges) const {
    std::map<std::string, std::set<std::string>> graph;
    std::set<std::pair<std::string, std::string>> unique;
    for (const WaitForEdge& edge : edges) {
        if (edge.waiter_id.empty() || edge.blocker_id.empty()
            || edge.waiter_id == edge.blocker_id) {
            throw std::invalid_argument("wait-for edge must connect distinct non-empty entities");
        }
        if (!unique.emplace(edge.waiter_id, edge.blocker_id).second) {
            throw std::invalid_argument("duplicate wait-for edge");
        }
        graph[edge.waiter_id].insert(edge.blocker_id);
        graph.try_emplace(edge.blocker_id);
    }

    std::map<std::string, std::size_t> index;
    std::map<std::string, std::size_t> low;
    std::set<std::string> on_stack;
    std::vector<std::string> stack;
    std::vector<std::vector<std::string>> cycles;
    std::size_t next_index = 0U;
    std::function<void(const std::string&)> visit = [&](const std::string& node) {
        index[node] = next_index;
        low[node] = next_index++;
        stack.push_back(node);
        on_stack.insert(node);
        for (const std::string& neighbor : graph.at(node)) {
            if (!index.contains(neighbor)) {
                visit(neighbor);
                low[node] = std::min(low[node], low[neighbor]);
            } else if (on_stack.contains(neighbor)) {
                low[node] = std::min(low[node], index[neighbor]);
            }
        }
        if (low[node] != index[node]) return;
        std::vector<std::string> component;
        while (!stack.empty()) {
            std::string member = std::move(stack.back());
            stack.pop_back();
            on_stack.erase(member);
            component.push_back(member);
            if (member == node) break;
        }
        std::sort(component.begin(), component.end());
        const bool self_cycle = component.size() == 1U
            && graph.at(component.front()).contains(component.front());
        if (component.size() > 1U || self_cycle) cycles.push_back(std::move(component));
    };
    for (const auto& [node, neighbors] : graph) {
        (void)neighbors;
        if (!index.contains(node)) visit(node);
    }
    std::sort(cycles.begin(), cycles.end());
    return cycles;
}

} // namespace simreality
