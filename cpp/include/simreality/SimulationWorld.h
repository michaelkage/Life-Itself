#pragma once

#include "simreality/CoreTypes.h"
#include "simreality/Districts.h"
#include "simreality/Ecosystem.h"
#include "simreality/Fixers.h"
#include "simreality/Gossip.h"
#include "simreality/LifeSystems.h"
#include "simreality/LaneTraffic.h"
#include "simreality/IntersectionTraffic.h"
#include "simreality/Justice.h"
#include "simreality/RandomStream.h"
#include "simreality/Reputation.h"
#include "simreality/SimulationRuntime.h"
#include "simreality/Spatial.h"
#include "simreality/Trauma.h"

#include <cstddef>
#include <cstdint>
#include <map>
#include <set>
#include <vector>

namespace simreality {

struct ResidentDayResult {
    EntityId entity_id{};
    BehaviourDecision behaviour{};
    TraumaAssessment trauma{};
};

struct DistrictDayResult {
    DistrictId district_id{};
    ScarState scars{};
    std::vector<ResidentDayResult> residents{};
};

struct WorldAdvanceReport {
    std::vector<ScheduledTick> ticks{};
    std::vector<DistrictDayResult> daily_results{};
    std::size_t memories_swept{0};
};

struct RouteSegmentRequest {
    std::string source_lane_id{};
    std::string destination_lane_id{};
    std::string entry_intersection_id{};
    std::string entry_movement_id{};
    std::string cleared_intersection_id{};
    std::string cleared_movement_id{};
    std::vector<SpatialPoint> lane_centerline{};
    double elapsed_seconds{0.0};
    double lookahead_distance{0.0};
    double desired_speed{0.0};
    double lane_maximum_acceleration{0.0};
    double collision_radius{0.5};
    double neighbor_collision_radius{0.5};
    double prediction_horizon_seconds{1.0};
    double maximum_avoidance_acceleration{0.0};
    double broadphase_radius{0.0};
};

struct RouteSegmentAdvanceResult {
    LaneFollowingResult movement{};
    bool source_lane_released{false};
    bool cleared_intersection_released{false};
};

// Portable coordinator for deterministic, simulation-time-driven world updates.
// Unreal-facing code should consume snapshots/reports rather than enter this core.
class SimulationWorld {
public:
    explicit SimulationWorld(
        WorldState initial_state = {}, double initial_hour = 0.0,
        std::uint64_t random_seed = 1U, double initial_real_time_seconds = 0.0);

    [[nodiscard]] WorldState& state() noexcept { return state_; }
    [[nodiscard]] const WorldState& state() const noexcept { return state_; }
    [[nodiscard]] std::vector<FixerNetwork>& fixer_networks() noexcept {
        return fixer_networks_;
    }
    [[nodiscard]] const std::vector<FixerNetwork>& fixer_networks() const noexcept {
        return fixer_networks_;
    }
    [[nodiscard]] double total_hours() const noexcept { return runtime_.total_hours(); }
    [[nodiscard]] double real_time_seconds() const noexcept { return runtime_.real_time_seconds(); }
    [[nodiscard]] std::uint64_t day_index() const noexcept { return runtime_.day_index(); }
    [[nodiscard]] RandomStream& random_stream() noexcept { return random_; }
    [[nodiscard]] LifeCoordinator& life_system() noexcept { return life_; }
    [[nodiscard]] const LifeCoordinator& life_system() const noexcept { return life_; }
    [[nodiscard]] std::uint64_t random_state() const noexcept { return random_.state(); }

    // Advances simulation time in a frame-rate-independent way. All due hourly
    // memory sweeps and daily district/NPC updates run in chronological order.
    [[nodiscard]] WorldAdvanceReport advance(
        double elapsed_hours, Weather visibility_weather = Weather::Clear,
        double weather_severity = 0.0);

    // Host-frame entry point: real time advances independently while the
    // simulation rate may be zero (paused) or scaled.
    [[nodiscard]] WorldAdvanceReport advance_frame(
        double elapsed_real_seconds, double simulation_hours_per_real_second,
        Weather visibility_weather = Weather::Clear,
        double weather_severity = 0.0);
    [[nodiscard]] GhostInfluenceResult attempt_ghost_influence(
        const EntityId& ghost_id, const EntityId& npc_id,
        const std::string& action, double hour_of_day);

    // Social transfer is allowed only between NPCs currently assigned to the same
    // district. The resulting conversation mutates the listener's memory state.
    [[nodiscard]] Conversation talk(const EntityId& listener_id, const EntityId& speaker_id);

    // Reputation is derived from the district's saved beliefs, not treated as
    // objective truth. Cooperation and resource-sharing use that standing plus
    // the donor's personal relationship with the recipient.
    [[nodiscard]] double community_reputation(
        const EntityId& target_id, const DistrictId& district_id) const;
    [[nodiscard]] double cooperation_score(
        const EntityId& from_id, const EntityId& to_id) const;
    [[nodiscard]] bool offer_support(
        const EntityId& from_id, const EntityId& to_id, double amount);

    // Records one observed action in the witnesses' local memories and applies
    // personal stress to witnesses and, when supplied, the victim.
    [[nodiscard]] std::size_t record_witnessed_action(
        const EntityId& actor_id, ActionTag action_tag, Description description,
        const std::vector<EntityId>& witness_ids, const EntityId& victim_id = {});
    [[nodiscard]] CriminalFile build_criminal_file(const EntityId& player_id) const;
    [[nodiscard]] ReputationProfile reputation_in_district(
        const DistrictId& district_id, const EntityId& player_id,
        const CriminalFile* criminal_file = nullptr) const;
    [[nodiscard]] Consequence resolve_offence(
        const DistrictId& district_id, const EntityId& player_id,
        ActionTag action_tag, const EntityId& officer_id, CriminalFile& criminal_file);
    [[nodiscard]] Negotiation approach_fixer(
        const DistrictId& district_id, const EntityId& player_id,
        const EntityId& fixer_id, double bribe, const CriminalFile* criminal_file = nullptr);

    // Optional spatial registration keeps physical coordinates separate from
    // the durable NPC schema while enabling deterministic nearby/perception queries.
    void set_npc_spatial_state(
        const EntityId& npc_id, SpatialPoint position, SpatialPoint forward,
        SpatialPoint velocity = {});
    [[nodiscard]] bool remove_npc_spatial_state(const EntityId& npc_id);
    [[nodiscard]] std::vector<EntityId> nearby_npcs(
        SpatialPoint center, double radius) const;

    // Lane admission is advanced on an explicit monotonic simulation tick.
    void configure_traffic_lane(const std::string& lane_id, std::size_t capacity);
    void advance_traffic_tick(std::uint64_t tick);
    [[nodiscard]] LaneTrafficResolution resolve_lane_traffic(
        const std::vector<LaneTrafficRequest>& requests);
    [[nodiscard]] bool release_lane_reservation(
        const std::string& lane_id, const EntityId& npc_id);

    // Intersection movements reserve all authored conflict zones atomically.
    void configure_intersection_movement(IntersectionMovementDefinition definition);
    void advance_intersection_tick(std::uint64_t tick);
    [[nodiscard]] IntersectionTrafficResolution resolve_intersection_traffic(
        const std::vector<IntersectionTrafficRequest>& requests);
    [[nodiscard]] bool release_intersection_reservation(
        const std::string& intersection_id, const EntityId& npc_id);
    // Advances one route segment under destination-lane admission and optional
    // intersection entry/clearance grants. Old occupancy is released only after
    // collision-aware movement succeeds, preventing reservation gaps.
    [[nodiscard]] RouteSegmentAdvanceResult advance_npc_on_reserved_route_segment(
        const EntityId& npc_id, const RouteSegmentRequest& request);
    [[nodiscard]] LaneFollowingResult advance_npc_on_reserved_intersection_movement(
        const EntityId& npc_id, const std::string& intersection_id,
        const std::string& movement_id,
        const std::vector<SpatialPoint>& lane_centerline,
        double elapsed_seconds, double lookahead_distance,
        double desired_speed, double maximum_acceleration);
    [[nodiscard]] LaneFollowingResult advance_npc_on_reserved_lane(
        const EntityId& npc_id, const std::string& lane_id,
        const std::vector<SpatialPoint>& lane_centerline,
        double elapsed_seconds, double lookahead_distance,
        double desired_speed, double maximum_acceleration);
    [[nodiscard]] LaneFollowingResult advance_npc_on_lane(
        const EntityId& npc_id, const std::vector<SpatialPoint>& lane_centerline,
        double elapsed_seconds, double lookahead_distance,
        double desired_speed, double maximum_acceleration);
    [[nodiscard]] LaneFollowingResult advance_npc_on_lane_avoiding_collisions(
        const EntityId& npc_id, const std::vector<SpatialPoint>& lane_centerline,
        double elapsed_seconds, double lookahead_distance,
        double desired_speed, double lane_maximum_acceleration,
        double collision_radius, double neighbor_collision_radius,
        double prediction_horizon_seconds, double maximum_avoidance_acceleration,
        double broadphase_radius);
    [[nodiscard]] std::vector<EntityId> visible_npcs(
        SpatialPoint target_position, double maximum_range,
        double field_of_view_radians,
        const std::set<EntityId>& occluded_npcs = {}) const;
    [[nodiscard]] std::vector<EntityId> audible_npcs(
        SpatialPoint source_position, double source_power,
        double maximum_range, double ambient_noise,
        const std::map<EntityId, double>& occlusion_attenuation = {}) const;
    [[nodiscard]] std::size_t record_spatially_witnessed_action(
        const EntityId& actor_id, ActionTag action_tag, Description description,
        double maximum_range, double field_of_view_radians,
        const std::set<EntityId>& occluded_npcs = {},
        const EntityId& victim_id = {});

private:
    [[nodiscard]] NPC& find_npc(const EntityId& entity_id);
    [[nodiscard]] const NPC& find_npc(const EntityId& entity_id) const;
    [[nodiscard]] WorldAdvanceReport advance_ticks(
        std::vector<ScheduledTick> ticks, Weather visibility_weather,
        double weather_severity);

    WorldState state_{};
    std::vector<FixerNetwork> fixer_networks_{};
    SimulationRuntime runtime_;
    RandomStream random_;
    LifeCoordinator life_{};
    SpatialPartition spatial_index_{10.0};
    LaneTrafficCoordinator lane_traffic_{};
    IntersectionTrafficCoordinator intersection_traffic_{};
    std::map<EntityId, SpatialPoint> npc_forward_{};
    std::map<EntityId, SpatialPoint> npc_velocity_{};
};

} // namespace simreality
