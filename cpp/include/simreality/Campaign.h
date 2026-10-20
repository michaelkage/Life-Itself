#pragma once

#include "simreality/SimulationWorld.h"

#include <cstdint>
#include <iosfwd>
#include <string>
#include <vector>

namespace simreality {

struct ArchivedTimeline {
    std::string archive_id{};
    std::string label{};
    EntityId character_id{};
    std::uint64_t death_day{0};
    std::uint64_t archived_day{0};
    std::string cause{};
    // Opaque binary world snapshot. It is never advanced in place.
    std::string snapshot{};
};

// Owns one active world plus immutable snapshots of worlds left behind by dead
// characters. A fresh life starts in a separate day-zero world.
class CampaignCoordinator {
public:
    explicit CampaignCoordinator(SimulationWorld initial_world = SimulationWorld{});

    [[nodiscard]] SimulationWorld& active_world() noexcept { return active_world_; }
    [[nodiscard]] const SimulationWorld& active_world() const noexcept { return active_world_; }
    [[nodiscard]] const std::vector<ArchivedTimeline>& archives() const noexcept { return archives_; }
    [[nodiscard]] const EntityId& active_character_id() const noexcept { return active_character_id_; }

    void begin_first_life(const EntityId& character_id);
    [[nodiscard]] bool record_death(std::string cause);
    [[nodiscard]] bool enter_ghost();
    [[nodiscard]] GhostInfluenceResult attempt_ghost_influence(
        const EntityId& npc_id, const std::string& action, double hour_of_day);
    [[nodiscard]] WorldAdvanceReport advance(
        double elapsed_hours, Weather visibility_weather = Weather::Clear,
        double weather_severity = 0.0);
    void start_new_life(const EntityId& character_id, WorldState initial_state = {},
                        std::uint64_t random_seed = 1U);

    // Returns a detached copy: callers may inspect it without changing the archive.
    [[nodiscard]] SimulationWorld inspect_archive(const std::string& archive_id) const;

private:
    friend void save_campaign(const CampaignCoordinator& campaign, std::ostream& output);
    friend CampaignCoordinator load_campaign(std::istream& input);

    SimulationWorld active_world_;
    EntityId active_character_id_{};
    std::vector<ArchivedTimeline> archives_{};
};

void save_campaign(const CampaignCoordinator& campaign, std::ostream& output);
[[nodiscard]] CampaignCoordinator load_campaign(std::istream& input);

} // namespace simreality
