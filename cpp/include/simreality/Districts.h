#pragma once

#include "simreality/CoreTypes.h"

namespace simreality {

inline constexpr double kScarEnterDI = 0.85;
inline constexpr double kScarExitDI = 0.60;
inline constexpr std::uint32_t kScarDaysRequired = 3;
inline constexpr std::uint32_t kScarRecoveryDays = 4;

struct ScarState {
    bool active{false};
    double intensity{0.0};
    std::uint32_t days_above_critical{0};
    double desperation_index{0.0};

    [[nodiscard]] bool boarded_windows() const noexcept;
    [[nodiscard]] bool derelict_facades() const noexcept;
    [[nodiscard]] bool police_ignore_minor_offences() const noexcept;
};

[[nodiscard]] double target_overpopulation(const District& district) noexcept;
[[nodiscard]] double target_supply_shortage(const District& district) noexcept;
[[nodiscard]] double target_corruption(const District& district) noexcept;
void evolve_inputs(District& district, double weather_severity);
[[nodiscard]] ScarState update_scars(District& district);
[[nodiscard]] ScarState tick_day(District& district, double weather_severity = 0.0);

} // namespace simreality
