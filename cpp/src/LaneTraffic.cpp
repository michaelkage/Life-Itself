#include "simreality/LaneTraffic.h"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <tuple>

namespace simreality {

LaneTrafficCoordinator::LaneTrafficCoordinator(std::uint64_t reservation_lease_ticks)
    : lease_ticks_(reservation_lease_ticks) {
    if (lease_ticks_ == 0U) {
        throw std::invalid_argument("reservation lease must be at least one tick");
    }
}

bool LaneTrafficCoordinator::WaitKey::operator<(const WaitKey& other) const noexcept {
    return std::tie(lane_id, entity_id) < std::tie(other.lane_id, other.entity_id);
}

void LaneTrafficCoordinator::configure_lane(
    const std::string& lane_id, std::size_t capacity) {
    if (lane_id.empty()) throw std::invalid_argument("lane id must not be empty");
    if (capacity == 0U) throw std::invalid_argument("lane capacity must be positive");
    const auto occupied = reservations_.find(lane_id);
    if (occupied != reservations_.end() && occupied->second.size() > capacity) {
        throw std::logic_error("new lane capacity is below active reservation count");
    }
    lane_capacity_[lane_id] = capacity;
}

void LaneTrafficCoordinator::advance_tick(std::uint64_t tick) {
    if (tick_initialized_ && tick <= current_tick_) {
        throw std::invalid_argument("traffic ticks must advance monotonically");
    }
    current_tick_ = tick;
    tick_initialized_ = true;

    for (auto lane = reservations_.begin(); lane != reservations_.end();) {
        auto& entries = lane->second;
        for (auto entry = entries.begin(); entry != entries.end();) {
            if (entry->second.expires_at_tick <= current_tick_) {
                entry = entries.erase(entry);
            } else {
                ++entry;
            }
        }
        if (entries.empty()) lane = reservations_.erase(lane);
        else ++lane;
    }
}

LaneTrafficResolution LaneTrafficCoordinator::resolve(
    const std::vector<LaneTrafficRequest>& requests) {
    if (!tick_initialized_) {
        throw std::logic_error("advance_tick must be called before resolving traffic");
    }

    std::set<WaitKey> unique_requests;
    std::set<std::string> requested_entities;
    for (const LaneTrafficRequest& request : requests) {
        if (request.lane_id.empty() || request.entity_id.empty()) {
            throw std::invalid_argument("traffic lane and entity ids must not be empty");
        }
        if (!lane_capacity_.contains(request.lane_id)) {
            throw std::out_of_range("traffic request references an unconfigured lane");
        }
        if (!unique_requests.insert({request.lane_id, request.entity_id}).second) {
            throw std::invalid_argument("duplicate entity request for the same lane");
        }
        if (!requested_entities.insert(request.entity_id).second) {
            throw std::invalid_argument("an entity may request only one lane per tick");
        }
    }

    if (!requests.empty()
        && current_tick_ > std::numeric_limits<std::uint64_t>::max() - lease_ticks_) {
        throw std::overflow_error("reservation expiry tick overflow");
    }
    for (auto wait = waiting_.begin(); wait != waiting_.end();) {
        if (!unique_requests.contains(wait->first)) wait = waiting_.erase(wait);
        else ++wait;
    }

    struct Candidate {
        LaneTrafficRequest request{};
        std::uint64_t wait_ticks{0U};
    };
    std::map<std::string, std::vector<Candidate>> by_lane;
    LaneTrafficResolution result;
    result.tick = current_tick_;

    for (const LaneTrafficRequest& request : requests) {
        auto& lane_reservations = reservations_[request.lane_id];
        const auto existing = lane_reservations.find(request.entity_id);
        if (existing != lane_reservations.end()) {
            existing->second.priority = request.priority;
            existing->second.expires_at_tick = current_tick_ + lease_ticks_;
            result.granted_entity_ids.push_back(request.entity_id);
            waiting_.erase({request.lane_id, request.entity_id});
            continue;
        }
        const WaitKey key{request.lane_id, request.entity_id};
        const auto wait = waiting_.find(key);
        by_lane[request.lane_id].push_back(Candidate{
            request, wait == waiting_.end() ? 0U : wait->second});
    }

    for (auto& [lane_id, candidates] : by_lane) {
        auto& active = reservations_[lane_id];
        const std::size_t capacity = lane_capacity_.at(lane_id);
        const std::size_t free_slots = capacity > active.size()
            ? capacity - active.size() : 0U;
        std::sort(candidates.begin(), candidates.end(),
            [](const Candidate& left, const Candidate& right) {
                if (left.request.priority != right.request.priority) {
                    return left.request.priority > right.request.priority;
                }
                if (left.wait_ticks != right.wait_ticks) {
                    return left.wait_ticks > right.wait_ticks;
                }
                return left.request.entity_id < right.request.entity_id;
            });

        for (std::size_t i = 0; i < candidates.size(); ++i) {
            const Candidate& candidate = candidates[i];
            const WaitKey key{lane_id, candidate.request.entity_id};
            if (i < free_slots) {
                active.emplace(candidate.request.entity_id, LaneReservation{
                    lane_id, candidate.request.entity_id,
                    current_tick_ + lease_ticks_, candidate.request.priority,
                    candidate.wait_ticks});
                waiting_.erase(key);
                result.granted_entity_ids.push_back(candidate.request.entity_id);
            } else {
                const std::uint64_t previous = candidate.wait_ticks;
                if (previous == std::numeric_limits<std::uint64_t>::max()) {
                    throw std::overflow_error("traffic wait counter overflow");
                }
                waiting_[key] = previous + 1U;
                result.denied_entity_ids.push_back(candidate.request.entity_id);
            }
        }
    }

    std::sort(result.granted_entity_ids.begin(), result.granted_entity_ids.end());
    std::sort(result.denied_entity_ids.begin(), result.denied_entity_ids.end());
    return result;
}

bool LaneTrafficCoordinator::release(
    const std::string& lane_id, const std::string& entity_id) {
    waiting_.erase({lane_id, entity_id});
    const auto lane = reservations_.find(lane_id);
    if (lane == reservations_.end()) return false;
    const bool removed = lane->second.erase(entity_id) != 0U;
    if (lane->second.empty()) reservations_.erase(lane);
    return removed;
}

bool LaneTrafficCoordinator::has_reservation(
    const std::string& lane_id, const std::string& entity_id) const {
    const auto lane = reservations_.find(lane_id);
    return lane != reservations_.end() && lane->second.contains(entity_id);
}

std::vector<LaneReservation> LaneTrafficCoordinator::reservations(
    const std::string& lane_id) const {
    const auto lane = reservations_.find(lane_id);
    if (lane == reservations_.end()) return {};
    std::vector<LaneReservation> result;
    result.reserve(lane->second.size());
    for (const auto& [entity_id, reservation] : lane->second) {
        (void)entity_id;
        result.push_back(reservation);
    }
    return result;
}

std::size_t LaneTrafficCoordinator::available_capacity(const std::string& lane_id) const {
    const auto capacity = lane_capacity_.find(lane_id);
    if (capacity == lane_capacity_.end()) {
        throw std::out_of_range("lane is not configured");
    }
    const auto lane = reservations_.find(lane_id);
    const std::size_t occupied = lane == reservations_.end() ? 0U : lane->second.size();
    return capacity->second > occupied ? capacity->second - occupied : 0U;
}

std::map<std::string, std::size_t> LaneTrafficCoordinator::occupancy_snapshot() const {
    std::map<std::string, std::size_t> result;
    for (const auto& [lane_id, entities] : reservations_) {
        result.emplace(lane_id, entities.size());
    }
    return result;
}

LaneTrafficSnapshot LaneTrafficCoordinator::snapshot() const {
    LaneTrafficSnapshot result;
    result.lease_ticks = lease_ticks_;
    result.current_tick = current_tick_;
    result.tick_initialized = tick_initialized_;
    result.capacities = lane_capacity_;
    for (const auto& [lane_id, entries] : reservations_) {
        (void)lane_id;
        for (const auto& [entity_id, reservation] : entries) {
            (void)entity_id; result.reservations.push_back(reservation);
        }
    }
    for (const auto& [key, ticks] : waiting_)
        result.waiting.push_back({key.lane_id, key.entity_id, ticks});
    return result;
}

void LaneTrafficCoordinator::restore(const LaneTrafficSnapshot& value) {
    if (value.lease_ticks == 0U || (!value.tick_initialized
        && (!value.reservations.empty() || !value.waiting.empty()))) {
        throw std::invalid_argument("lane traffic snapshot clock or lease is invalid");
    }
    std::map<std::string, std::map<std::string, LaneReservation>> reservations;
    for (const auto& [lane, capacity] : value.capacities) {
        if (lane.empty() || capacity == 0U) throw std::invalid_argument("invalid lane capacity snapshot");
    }
    for (const auto& reservation : value.reservations) {
        const auto cap = value.capacities.find(reservation.lane_id);
        if (reservation.lane_id.empty() || reservation.entity_id.empty()
            || cap == value.capacities.end()
            || (value.tick_initialized && reservation.expires_at_tick <= value.current_tick)
            || !reservations[reservation.lane_id].emplace(
                reservation.entity_id, reservation).second) {
            throw std::invalid_argument("invalid or duplicate lane reservation snapshot");
        }
    }
    for (const auto& [lane, entries] : reservations) {
        if (entries.size() > value.capacities.at(lane))
            throw std::invalid_argument("lane snapshot exceeds configured capacity");
    }
    std::map<WaitKey, std::uint64_t> waiting;
    for (const auto& item : value.waiting) {
        if (item.lane_id.empty() || item.entity_id.empty()
            || !value.capacities.contains(item.lane_id)
            || (reservations.contains(item.lane_id)
                && reservations.at(item.lane_id).contains(item.entity_id))
            || !waiting.emplace(WaitKey{item.lane_id, item.entity_id}, item.wait_ticks).second) {
            throw std::invalid_argument("invalid or duplicate lane waiting snapshot");
        }
    }
    lease_ticks_ = value.lease_ticks;
    current_tick_ = value.current_tick;
    tick_initialized_ = value.tick_initialized;
    lane_capacity_ = value.capacities;
    reservations_ = std::move(reservations);
    waiting_ = std::move(waiting);
}

} // namespace simreality
