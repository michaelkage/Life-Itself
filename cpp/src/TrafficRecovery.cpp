#include "simreality/TrafficRecovery.h"
#include "simreality/RoutePlanning.h"

#include <algorithm>
#include <functional>
#include <set>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace simreality {

void JourneyReservationManager::track(JourneyOccupancy occupancy) {
    if (occupancy.entity_id.empty() || occupancy.lane_id.empty()
        || (occupancy.intersection_id.empty() != occupancy.movement_id.empty())) {
        throw std::invalid_argument("journey occupancy identifiers are incomplete");
    }
    const auto found = tracked_.find(occupancy.entity_id);
    if (found != tracked_.end()
        && (found->second.lane_id != occupancy.lane_id
            || found->second.intersection_id != occupancy.intersection_id
            || found->second.movement_id != occupancy.movement_id)) {
        throw std::logic_error(
            "journey occupancy changes require confirmed clearance and explicit retracking");
    }
    tracked_[occupancy.entity_id] = std::move(occupancy);
}


std::vector<JourneyOccupancy> JourneyReservationManager::snapshot() const {
    std::vector<JourneyOccupancy> result;
    result.reserve(tracked_.size());
    for (const auto& [entity_id, occupancy] : tracked_) {
        (void)entity_id; result.push_back(occupancy);
    }
    return result;
}

void JourneyReservationManager::restore(const std::vector<JourneyOccupancy>& value) {
    std::map<std::string, JourneyOccupancy> restored;
    for (const auto& occupancy : value) {
        if (occupancy.entity_id.empty() || occupancy.lane_id.empty()
            || (occupancy.intersection_id.empty() != occupancy.movement_id.empty())
            || !restored.emplace(occupancy.entity_id, occupancy).second) {
            throw std::invalid_argument("invalid or duplicate journey occupancy checkpoint");
        }
    }
    tracked_ = std::move(restored);
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

std::vector<DeadlockResolutionProposal> TrafficDeadlockDetector::propose_resolutions(
    const std::vector<WaitForResourceEdge>& edges,
    const std::map<std::string, std::pair<std::vector<LaneTrafficRequest>,
        std::vector<IntersectionTrafficRequest>>>& replacement_reservations) const {
    std::vector<WaitForEdge> graph_edges;
    graph_edges.reserve(edges.size());
    std::set<std::tuple<std::string, std::string, BlockedResourceKind, std::string>> unique;
    std::set<std::pair<std::string, std::string>> graph_unique;
    for (const auto& edge : edges) {
        if (edge.waiter_id.empty() || edge.blocker_id.empty()
            || edge.waiter_id == edge.blocker_id || edge.resource_id.empty()
            || (edge.resource_kind != BlockedResourceKind::Lane
                && edge.resource_kind != BlockedResourceKind::Intersection)) {
            throw std::invalid_argument("resource wait edge is malformed");
        }
        if (!unique.emplace(edge.waiter_id, edge.blocker_id,
                edge.resource_kind, edge.resource_id).second) {
            throw std::invalid_argument("duplicate resource wait edge");
        }
        if (graph_unique.emplace(edge.waiter_id, edge.blocker_id).second)
            graph_edges.push_back({edge.waiter_id, edge.blocker_id});
    }
    const auto cycles = detect(graph_edges);
    std::vector<DeadlockResolutionProposal> proposals;
    for (const auto& cycle : cycles) {
        const std::set<std::string> members(cycle.begin(), cycle.end());
        const std::string* yielding = nullptr;
        for (const std::string& participant : cycle) {
            const auto candidate = replacement_reservations.find(participant);
            if (candidate == replacement_reservations.end()) continue;
            const bool has_alternative = !candidate->second.first.empty()
                || !candidate->second.second.empty();
            if (has_alternative) { yielding = &participant; break; }
        }
        if (yielding == nullptr) continue;

        DeadlockResolutionProposal proposal;
        proposal.participants = cycle;
        proposal.yielding_entity_id = *yielding;
        std::set<std::tuple<BlockedResourceKind, std::string, std::string>> resources;
        for (const auto& edge : edges) {
            if (members.contains(edge.waiter_id) && members.contains(edge.blocker_id)) {
                resources.emplace(edge.resource_kind, edge.resource_id, edge.blocker_id);
            }
        }
        for (const auto& [kind, resource_id, owner] : resources) {
            proposal.blocking_resources.push_back({kind, resource_id, owner});
        }
        const auto& replacements = replacement_reservations.at(*yielding);
        for (const auto& request : replacements.first) {
            if (request.entity_id != *yielding || request.lane_id.empty()) {
                throw std::invalid_argument("replacement lane reservation belongs to another entity");
            }
        }
        for (const auto& request : replacements.second) {
            if (request.entity_id != *yielding || request.intersection_id.empty()
                || request.movement_id.empty()) {
                throw std::invalid_argument("replacement intersection reservation belongs to another entity");
            }
        }
        proposal.replacement_lane_requests = replacements.first;
        proposal.replacement_intersection_requests = replacements.second;
        proposals.push_back(std::move(proposal));
    }
    return proposals;
}

} // namespace simreality
