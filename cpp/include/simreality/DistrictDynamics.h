#pragma once

#include "simreality/CoreTypes.h"

namespace simreality {

inline constexpr double kOverpopulationReversion = 0.15;
inline constexpr double kSupplyPersistence = 0.75;
inline constexpr double kSupplyBaseline = 0.15;
inline constexpr double kSupplyCrowdingWeight = 0.7;
inline constexpr double kCorruptionRise = 0.12;
inline constexpr double kCorruptionFall = 0.01;
inline constexpr double kCorruptionPressure = 0.8;
inline constexpr double kCorruptionSecurityWeight = 0.4;
inline constexpr double kWeatherReversion = 0.4;

inline constexpr double kScarEnterDI = 0.85;
inline constexpr double kScarExitDI = 0.60;
inline constexpr std::uint32_t kScarDaysRequired = 3;
inline constexpr std::uint32_t kScarRecoveryDays = 4;
inline constexpr double kScarRiseRate = 0.34;
inline constexpr double kScarFallRate = 0.25;

struct ScarState {
    bool active{false};
    double intensity{0.0};
    std::uint32_t days_above_critical{0};
    double desperation_index{0.0};

    [[nodiscard]] bool boarded_windows() const noexcept {
        return active && intensity > 0.3;
    }
    [[nodiscard]] bool derelict_facades() const noexcept {
        return intensity > 0.6;
    }
    [[nodiscard]] bool police_ignore_minor_offences() const noexcept {
        return active;
    }
};

[[nodiscard]] double desperation_index(const District& district) noexcept;
[[nodiscard]] double target_overpopulation(const District& district) noexcept;
[[nodiscard]] double target_supply_shortage(const District& district) noexcept;
[[nodiscard]] double target_corruption(const District& district) noexcept;
void evolve_inputs(District& district, double weather_severity);
[[nodiscard]] ScarState update_scars(District& district) noexcept;
[[nodiscard]] ScarState tick_day(District& district, double weather_severity = 0.0);

} // namespace simreality
