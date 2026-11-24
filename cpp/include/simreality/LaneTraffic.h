#pragma once

#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace simreality {

struct LaneTrafficRequest {
    std::string lane_id{};
    std::string entity_id{};
    std::int32_t priority{0};
};

struct LaneTrafficResolution {
    std::uint64_t tick{0};
    std::vector<std::string> granted_entity_ids{};
    std::vector<std::string> denied_entity_ids{};
};

struct LaneReservation {
    std::string lane_id{};
    std::string entity_id{};
    std::uint64_t expires_at_tick{0};
    std::int32_t priority{0};
    std::uint64_t consecutive_wait_ticks{0};
};

// Deterministic, tick-driven lane admission control. It models exclusive lane
// slots, not geometric collision detection; callers retain physical occupancy
// and must release a reservation when an agent leaves or changes lanes.
class LaneTrafficCoordinator {
public:
    explicit LaneTrafficCoordinator(std::uint64_t reservation_lease_ticks = 2U);

    void configure_lane(const std::string& lane_id, std::size_t capacity);
    void advance_tick(std::uint64_t tick);
    [[nodiscard]] LaneTrafficResolution resolve(
        const std::vector<LaneTrafficRequest>& requests);
    [[nodiscard]] bool release(const std::string& lane_id, const std::string& entity_id);
    [[nodiscard]] bool has_reservation(
        const std::string& lane_id, const std::string& entity_id) const;
    [[nodiscard]] std::vector<LaneReservation> reservations(
        const std::string& lane_id) const;
    [[nodiscard]] std::size_t available_capacity(const std::string& lane_id) const;
    [[nodiscard]] std::uint64_t current_tick() const noexcept { return current_tick_; }

private:
    struct WaitKey {
        std::string lane_id{};
        std::string entity_id{};
        [[nodiscard]] bool operator<(const WaitKey& other) const noexcept;
    };

    std::uint64_t lease_ticks_{2U};
    std::uint64_t current_tick_{0U};
    bool tick_initialized_{false};
    std::map<std::string, std::size_t> lane_capacity_{};
    std::map<std::string, std::map<std::string, LaneReservation>> reservations_{};
    std::map<WaitKey, std::uint64_t> waiting_{};
};

} // namespace simreality
