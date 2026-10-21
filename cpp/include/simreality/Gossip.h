#pragma once

#include "simreality/CoreTypes.h"

#include <optional>
#include <string>
#include <vector>

namespace simreality {

inline constexpr double kFloorUnattributedRumour = 0.01;
inline constexpr double kFloorAttributedRumour = 0.05;

struct Rumour {
    std::string action_tag{};
    EntityId target_entity_id{};
    Description description{};
    double retention{1.0};
    DistrictId district_id{};
    std::uint32_t corroborations{1};
    SimulationHour timestamp_hour{0.0};
    EntityId source_entity_id{};
    double source_reliability{0.5};

    [[nodiscard]] bool is_attributable() const noexcept {
        return !target_entity_id.empty();
    }
};

struct Conversation {
    EntityId npc_a{};
    EntityId npc_b{};
    DistrictId district_id{};
    std::vector<Rumour> transferred{};
};

[[nodiscard]] double jacket_confidence(const Description& description) noexcept;
[[nodiscard]] std::string describe(const Description& description);
[[nodiscard]] Description merge_descriptions(
    const Description& first, const Description& second, double speaker_fidelity = 1.0);
[[nodiscard]] Rumour corroborate(const Rumour& first, const Rumour& second);
[[nodiscard]] std::optional<Rumour> retell(const NPCMemory& memory);
[[nodiscard]] Conversation converse(
    NPC& listener, const NPC& speaker, const DistrictId& district_id = {});
[[nodiscard]] std::string police_response(const Rumour& rumour, const DistrictId& district_id);

} // namespace simreality
