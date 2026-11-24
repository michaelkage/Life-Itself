#include "simreality/IntersectionTraffic.h"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <tuple>

namespace simreality {

IntersectionTrafficCoordinator::IntersectionTrafficCoordinator(std::uint64_t lease_ticks)
    : lease_ticks_(lease_ticks) {
    if (lease_ticks_ == 0U) {
        throw std::invalid_argument("intersection reservation lease must be positive");
    }
}

bool IntersectionTrafficCoordinator::MovementKey::operator<(
    const MovementKey& other) const noexcept {
    return std::tie(intersection_id, movement_id)
        < std::tie(other.intersection_id, other.movement_id);
}

bool IntersectionTrafficCoordinator::WaitKey::operator<(
    const WaitKey& other) const noexcept {
    return std::tie(intersection_id, entity_id)
        < std::tie(other.intersection_id, other.entity_id);
}

void IntersectionTrafficCoordinator::configure_movement(
    IntersectionMovementDefinition definition) {
    if (definition.intersection_id.empty() || definition.movement_id.empty()
        || definition.conflict_zone_ids.empty()) {
        throw std::invalid_argument(
            "intersection, movement, and at least one conflict-zone id are required");
    }
    for (const std::string& zone : definition.conflict_zone_ids) {
        if (zone.empty()) throw std::invalid_argument("conflict-zone ids must not be empty");
    }
    const MovementKey key{definition.intersection_id, definition.movement_id};
    movements_[key] = std::move(definition);
}

void IntersectionTrafficCoordinator::advance_tick(std::uint64_t tick) {
    if (tick_initialized_ && tick <= current_tick_) {
        throw std::invalid_argument("intersection ticks must advance monotonically");
    }
    current_tick_ = tick;
    tick_initialized_ = true;
    for (auto intersection = reservations_.begin();
         intersection != reservations_.end();) {
        auto& active = intersection->second;
        for (auto reservation = active.begin(); reservation != active.end();) {
            if (reservation->second.expires_at_tick <= current_tick_) {
                reservation = active.erase(reservation);
            } else {
                ++reservation;
            }
        }
        if (active.empty()) intersection = reservations_.erase(intersection);
        else ++intersection;
    }
}

bool IntersectionTrafficCoordinator::conflicts(
    const IntersectionMovementDefinition& left,
    const IntersectionMovementDefinition& right) const {
    auto a = left.conflict_zone_ids.begin();
    auto b = right.conflict_zone_ids.begin();
    while (a != left.conflict_zone_ids.end() && b != right.conflict_zone_ids.end()) {
        if (*a == *b) return true;
        if (*a < *b) ++a;
        else ++b;
    }
    return false;
}

IntersectionTrafficResolution IntersectionTrafficCoordinator::resolve(
    const std::vector<IntersectionTrafficRequest>& requests) {
    if (!tick_initialized_) {
        throw std::logic_error("advance_tick must precede intersection resolution");
    }
    std::set<WaitKey> requested;
    std::set<std::string> entities;
    for (const auto& request : requests) {
        if (request.intersection_id.empty() || request.movement_id.empty()
            || request.entity_id.empty()) {
            throw std::invalid_argument("intersection request identifiers must not be empty");
        }
        if (!movements_.contains({request.intersection_id, request.movement_id})) {
            throw std::out_of_range("request references an unconfigured intersection movement");
        }
        if (!requested.insert({request.intersection_id, request.entity_id}).second) {
            throw std::invalid_argument("entity may submit only one movement per intersection tick");
        }
        if (!entities.insert(request.entity_id).second) {
            throw std::invalid_argument("entity may request only one intersection per tick");
        }
    }
    if (!requests.empty()
        && current_tick_ > std::numeric_limits<std::uint64_t>::max() - lease_ticks_) {
        throw std::overflow_error("intersection reservation expiry overflow");
    }
    for (auto wait = waiting_.begin(); wait != waiting_.end();) {
        if (!requested.contains(wait->first)) wait = waiting_.erase(wait);
        else ++wait;
    }

    struct Candidate {
        IntersectionTrafficRequest request{};
        const IntersectionMovementDefinition* definition{nullptr};
        std::uint64_t wait_ticks{0U};
    };
    std::vector<Candidate> candidates;
    candidates.reserve(requests.size());
    IntersectionTrafficResolution result;
    result.tick = current_tick_;

    for (const auto& request : requests) {
        const MovementKey movement_key{request.intersection_id, request.movement_id};
        const auto& definition = movements_.at(movement_key);
        auto& active = reservations_[request.intersection_id];
        const auto existing = active.find(request.entity_id);
        if (existing != active.end()) {
            if (existing->second.movement_id != request.movement_id) {
                throw std::logic_error("entity cannot change movement while holding an intersection reservation");
            }
            existing->second.priority = request.priority;
            existing->second.expires_at_tick = current_tick_ + lease_ticks_;
            result.granted_entity_ids.push_back(request.entity_id);
            waiting_.erase({request.intersection_id, request.entity_id});
            continue;
        }
        const WaitKey wait_key{request.intersection_id, request.entity_id};
        const auto wait = waiting_.find(wait_key);
        candidates.push_back({request, &definition,
            wait == waiting_.end() ? 0U : wait->second});
    }

    std::sort(candidates.begin(), candidates.end(),
        [](const Candidate& left, const Candidate& right) {
            if (left.request.priority != right.request.priority)
                return left.request.priority > right.request.priority;
            if (left.wait_ticks != right.wait_ticks)
                return left.wait_ticks > right.wait_ticks;
            if (left.request.intersection_id != right.request.intersection_id)
                return left.request.intersection_id < right.request.intersection_id;
            return left.request.entity_id < right.request.entity_id;
        });

    for (const Candidate& candidate : candidates) {
        auto& active = reservations_[candidate.request.intersection_id];
        bool blocked = false;
        for (const auto& [entity_id, reservation] : active) {
            (void)entity_id;
            const auto definition = movements_.find(
                {reservation.intersection_id, reservation.movement_id});
            if (definition == movements_.end()) {
                throw std::logic_error("active reservation references a missing movement definition");
            }
            if (conflicts(*candidate.definition, definition->second)) {
                blocked = true;
                break;
            }
        }
        const WaitKey key{candidate.request.intersection_id, candidate.request.entity_id};
        if (!blocked) {
            active.emplace(candidate.request.entity_id, IntersectionReservation{
                candidate.request.intersection_id, candidate.request.movement_id,
                candidate.request.entity_id, current_tick_ + lease_ticks_,
                candidate.request.priority, candidate.wait_ticks});
            waiting_.erase(key);
            result.granted_entity_ids.push_back(candidate.request.entity_id);
        } else {
            if (candidate.wait_ticks == std::numeric_limits<std::uint64_t>::max()) {
                throw std::overflow_error("intersection wait counter overflow");
            }
            waiting_[key] = candidate.wait_ticks + 1U;
            result.denied_entity_ids.push_back(candidate.request.entity_id);
        }
    }

    std::sort(result.granted_entity_ids.begin(), result.granted_entity_ids.end());
    std::sort(result.denied_entity_ids.begin(), result.denied_entity_ids.end());
    return result;
}

bool IntersectionTrafficCoordinator::release(
    const std::string& intersection_id, const std::string& entity_id) {
    waiting_.erase({intersection_id, entity_id});
    const auto intersection = reservations_.find(intersection_id);
    if (intersection == reservations_.end()) return false;
    const bool removed = intersection->second.erase(entity_id) != 0U;
    if (intersection->second.empty()) reservations_.erase(intersection);
    return removed;
}

bool IntersectionTrafficCoordinator::has_reservation(
    const std::string& intersection_id, const std::string& movement_id,
    const std::string& entity_id) const {
    const auto intersection = reservations_.find(intersection_id);
    if (intersection == reservations_.end()) return false;
    const auto reservation = intersection->second.find(entity_id);
    return reservation != intersection->second.end()
        && reservation->second.movement_id == movement_id;
}

std::vector<IntersectionReservation> IntersectionTrafficCoordinator::reservations(
    const std::string& intersection_id) const {
    const auto intersection = reservations_.find(intersection_id);
    if (intersection == reservations_.end()) return {};
    std::vector<IntersectionReservation> result;
    result.reserve(intersection->second.size());
    for (const auto& [entity_id, reservation] : intersection->second) {
        (void)entity_id;
        result.push_back(reservation);
    }
    return result;
}

} // namespace simreality
