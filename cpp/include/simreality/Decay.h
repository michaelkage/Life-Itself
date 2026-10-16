#pragma once

#include "simreality/CoreTypes.h"

#include <optional>
#include <vector>

namespace simreality {

inline constexpr double kLambdaBase = 0.02;
inline constexpr double kTelephoneThreshold = 0.6;

[[nodiscard]] double visibility_modifier(double game_hour, Weather weather) noexcept;
[[nodiscard]] double decay_constant(
    AgeBand age_band,
    ActionTag action_tag,
    double game_hour,
    Weather weather,
    std::optional<double> lambda_base = std::nullopt) noexcept;

[[nodiscard]] double retention_after(
    const NPCMemory& memory,
    AgeBand age_band,
    double current_hour,
    Weather weather,
    std::optional<double> lambda_base = std::nullopt) noexcept;

[[nodiscard]] std::vector<NPCMemory> sweep(
    const std::vector<NPCMemory>& memories,
    AgeBand age_band,
    double current_hour,
    Weather weather,
    std::optional<double> lambda_base = std::nullopt);

} // namespace simreality
