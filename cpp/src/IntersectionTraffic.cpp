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
    const auto existing = movements_.find(key);
    if (existing != movements_.end()
        && existing->second.conflict_zone_ids != definition.conflict_zone_ids) {
        const auto intersection = reservations_.find(definition.intersection_id);
        if (intersection != reservations_.end()) {
            const bool occupied = std::any_of(
                intersection->second.begin(), intersection->second.end(),
                [&definition](const auto& entry) {
                    return entry.second.movement_id == definition.movement_id;
                });
            if (occupied) {
                throw std::logic_error(
                    "cannot change conflict zones while the movement has active reservations");
            }
        }
    }
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

std::size_t IntersectionTrafficCoordinator::conflict_pressure(
    const std::string& intersection_id, const std::string& movement_id) const {
    const auto target = movements_.find({intersection_id, movement_id});
    if (target == movements_.end()) throw std::out_of_range("unknown intersection movement");
    const auto active = reservations_.find(intersection_id);
    if (active == reservations_.end()) return 0U;
    std::size_t pressure = 0U;
    for (const auto& [entity_id, reservation] : active->second) {
        (void)entity_id;
        const auto occupied = movements_.find({intersection_id, reservation.movement_id});
        if (occupied == movements_.end()) throw std::logic_error("reservation references unknown movement");
        if (conflicts(target->second, occupied->second)) ++pressure;
    }
    return pressure;
}

std::map<std::pair<std::string, std::string>, std::size_t>
IntersectionTrafficCoordinator::conflict_pressure_snapshot() const {
    std::map<std::pair<std::string, std::string>, std::size_t> result;
    for (const auto& [key, definition] : movements_) {
        (void)definition;
        result.emplace(std::make_pair(key.intersection_id, key.movement_id),
            conflict_pressure(key.intersection_id, key.movement_id));
    }
    return result;
}

IntersectionTrafficSnapshot IntersectionTrafficCoordinator::snapshot() const {
    IntersectionTrafficSnapshot result;
    result.lease_ticks = lease_ticks_;
    result.current_tick = current_tick_;
    result.tick_initialized = tick_initialized_;
    for (const auto& [key, definition] : movements_) {
        (void)key; result.movements.push_back(definition);
    }
    for (const auto& [intersection, entries] : reservations_) {
        (void)intersection;
        for (const auto& [entity, reservation] : entries) {
            (void)entity; result.reservations.push_back(reservation);
        }
    }
    for (const auto& [key, ticks] : waiting_)
        result.waiting.push_back({key.intersection_id, key.entity_id, ticks});
    return result;
}

void IntersectionTrafficCoordinator::restore(const IntersectionTrafficSnapshot& value) {
    if (value.lease_ticks == 0U || (!value.tick_initialized
        && (!value.reservations.empty() || !value.waiting.empty()))) {
        throw std::invalid_argument("intersection traffic snapshot clock or lease is invalid");
    }
    std::map<MovementKey, IntersectionMovementDefinition> movements;
    for (const auto& definition : value.movements) {
        if (definition.intersection_id.empty() || definition.movement_id.empty()
            || definition.conflict_zone_ids.empty()
            || std::any_of(definition.conflict_zone_ids.begin(), definition.conflict_zone_ids.end(),
                [](const std::string& zone) { return zone.empty(); })
            || !movements.emplace(MovementKey{definition.intersection_id, definition.movement_id},
                definition).second) {
            throw std::invalid_argument("invalid or duplicate intersection movement snapshot");
        }
    }
    std::map<std::string, std::map<std::string, IntersectionReservation>> reservations;
    for (const auto& reservation : value.reservations) {
        const MovementKey key{reservation.intersection_id, reservation.movement_id};
        if (reservation.intersection_id.empty() || reservation.movement_id.empty()
            || reservation.entity_id.empty() || !movements.contains(key)
            || (value.tick_initialized && reservation.expires_at_tick <= value.current_tick)
            || !reservations[reservation.intersection_id].emplace(
                reservation.entity_id, reservation).second) {
            throw std::invalid_argument("invalid or duplicate intersection reservation snapshot");
        }
    }
    for (const auto& [intersection, entries] : reservations) {
        (void)intersection;
        for (auto left = entries.begin(); left != entries.end(); ++left) {
            for (auto right = std::next(left); right != entries.end(); ++right) {
                const auto& a = movements.at({left->second.intersection_id, left->second.movement_id});
                const auto& b = movements.at({right->second.intersection_id, right->second.movement_id});
                if (conflicts(a, b))
                    throw std::invalid_argument("snapshot contains conflicting active reservations");
            }
        }
    }
    std::map<WaitKey, std::uint64_t> waiting;
    for (const auto& item : value.waiting) {
        if (item.intersection_id.empty() || item.entity_id.empty()
            || (reservations.contains(item.intersection_id)
                && reservations.at(item.intersection_id).contains(item.entity_id))
            || !waiting.emplace(WaitKey{item.intersection_id, item.entity_id}, item.wait_ticks).second) {
            throw std::invalid_argument("invalid or duplicate intersection waiting snapshot");
        }
    }
    lease_ticks_ = value.lease_ticks;
    current_tick_ = value.current_tick;
    tick_initialized_ = value.tick_initialized;
    movements_ = std::move(movements);
    reservations_ = std::move(reservations);
    waiting_ = std::move(waiting);
}

} // namespace simreality
