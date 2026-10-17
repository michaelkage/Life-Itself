#pragma once

#include "simreality/CoreTypes.h"

#include <string>

namespace simreality {

inline constexpr double kStressRetainedPerDay = 0.97;
inline constexpr double kTierAnxiousStress = 0.10;
inline constexpr double kTierParanoidStress = 0.45;

struct TraumaAssessment {
    TraumaLevel level{TraumaLevel::Baseline};
    double personal_stress{0.0};
    double desperation_index{0.0};
    std::string source{};

    [[nodiscard]] bool permanent() const noexcept {
        return level == TraumaLevel::Vigilante;
    }
};

[[nodiscard]] double relieve(double days, double stress) noexcept;
[[nodiscard]] double absorb(NPC& npc, ActionTag action_tag, bool was_victim = false) noexcept;
[[nodiscard]] TraumaLevel personal_level(double stress) noexcept;
[[nodiscard]] TraumaAssessment assess(const NPC& npc, double desperation_index);
[[nodiscard]] TraumaAssessment daily_update(
    NPC& npc, double desperation_index, double days = 1.0);

} // namespace simreality
