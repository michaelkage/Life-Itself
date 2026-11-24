#pragma once

#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace simreality {

struct IntersectionMovementDefinition {
    std::string intersection_id{};
    std::string movement_id{};
    std::set<std::string> conflict_zone_ids{};
};

struct IntersectionTrafficRequest {
    std::string intersection_id{};
    std::string movement_id{};
    std::string entity_id{};
    std::int32_t priority{0};
};

struct IntersectionTrafficResolution {
    std::uint64_t tick{0};
    std::vector<std::string> granted_entity_ids{};
    std::vector<std::string> denied_entity_ids{};
};

struct IntersectionReservation {
    std::string intersection_id{};
    std::string movement_id{};
    std::string entity_id{};
    std::uint64_t expires_at_tick{0};
    std::int32_t priority{0};
    std::uint64_t consecutive_wait_ticks{0};
};

struct IntersectionWaitRecord { std::string intersection_id{}; std::string entity_id{}; std::uint64_t wait_ticks{0}; };
struct IntersectionTrafficSnapshot {
    std::uint64_t lease_ticks{2U}, current_tick{0U};
    bool tick_initialized{false};
    std::vector<IntersectionMovementDefinition> movements{};
    std::vector<IntersectionReservation> reservations{};
    std::vector<IntersectionWaitRecord> waiting{};
};

// Atomically reserves every authored conflict zone for a movement. Movements
// with disjoint zones may proceed concurrently; geometry remains host-authored.
class IntersectionTrafficCoordinator {
public:
    explicit IntersectionTrafficCoordinator(std::uint64_t lease_ticks = 2U);

    void configure_movement(IntersectionMovementDefinition definition);
    void advance_tick(std::uint64_t tick);
    [[nodiscard]] IntersectionTrafficResolution resolve(
        const std::vector<IntersectionTrafficRequest>& requests);
    [[nodiscard]] bool release(
        const std::string& intersection_id, const std::string& entity_id);
    [[nodiscard]] bool has_reservation(
        const std::string& intersection_id, const std::string& movement_id,
        const std::string& entity_id) const;
    [[nodiscard]] std::vector<IntersectionReservation> reservations(
        const std::string& intersection_id) const;
    [[nodiscard]] std::size_t conflict_pressure(
        const std::string& intersection_id, const std::string& movement_id) const;
    [[nodiscard]] std::map<std::pair<std::string, std::string>, std::size_t>
        conflict_pressure_snapshot() const;
    [[nodiscard]] IntersectionTrafficSnapshot snapshot() const;
    void restore(const IntersectionTrafficSnapshot& snapshot);
    [[nodiscard]] std::uint64_t current_tick() const noexcept { return current_tick_; }

private:
    struct MovementKey {
        std::string intersection_id{};
        std::string movement_id{};
        [[nodiscard]] bool operator<(const MovementKey& other) const noexcept;
    };
    struct WaitKey {
        std::string intersection_id{};
        std::string entity_id{};
        [[nodiscard]] bool operator<(const WaitKey& other) const noexcept;
    };

    [[nodiscard]] bool conflicts(
        const IntersectionMovementDefinition& left,
        const IntersectionMovementDefinition& right) const;

    std::uint64_t lease_ticks_{2U};
    std::uint64_t current_tick_{0U};
    bool tick_initialized_{false};
    std::map<MovementKey, IntersectionMovementDefinition> movements_{};
    std::map<std::string, std::map<std::string, IntersectionReservation>> reservations_{};
    std::map<WaitKey, std::uint64_t> waiting_{};
};

} // namespace simreality
