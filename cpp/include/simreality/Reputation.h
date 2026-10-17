#pragma once

#include "simreality/Justice.h"

#include <vector>

namespace simreality {

inline constexpr double kAccusationGain = 0.7;
inline constexpr double kRecordFloor = 0.15;
inline constexpr double kRecordDecayPerDay = 0.98;

struct ReputationProfile {
    double reputation{1.0};
    double accusation_penalty{0.0};
    double record_penalty{0.0};

    [[nodiscard]] const char* source() const noexcept;
    [[nodiscard]] bool clean() const noexcept;
};

[[nodiscard]] double accusation_penalty(
    const std::vector<NPCMemory>& memories, const EntityId& player_id);
[[nodiscard]] double record_penalty(
    const CriminalFile* criminal_file, std::uint32_t current_day);
[[nodiscard]] ReputationProfile local_reputation(
    const std::vector<NPCMemory>& memories, const EntityId& player_id,
    const CriminalFile* criminal_file = nullptr, std::uint32_t current_day = 0);

} // namespace simreality
