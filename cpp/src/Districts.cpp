#include "simreality/Districts.h"

#include "simreality/Ecosystem.h"

#include <algorithm>

namespace simreality {
namespace {
constexpr double kOverpopulationReversion = 0.15;
constexpr double kSupplyPersistence = 0.75;
constexpr double kSupplyBaseline = 0.15;
constexpr double kSupplyCrowdingWeight = 0.7;
constexpr double kCorruptionRise = 0.12;
constexpr double kCorruptionFall = 0.01;
constexpr double kCorruptionPressure = 0.8;
constexpr double kCorruptionSecurityWeight = 0.4;
constexpr double kWeatherReversion = 0.4;
constexpr double kScarRiseRate = 0.34;
constexpr double kScarFallRate = 0.25;
}

bool ScarState::boarded_windows() const noexcept {
    return active && intensity > 0.3;
}

bool ScarState::derelict_facades() const noexcept {
    return intensity > 0.6;
}

bool ScarState::police_ignore_minor_offences() const noexcept {
    return active;
}

double target_overpopulation(const District& district) noexcept {
    if (district.capacity == 0) return 1.0;
    return std::clamp(static_cast<double>(district.population) /
        static_cast<double>(district.capacity), 0.0, 1.0);
}

double target_supply_shortage(const District& district) noexcept {
    return std::clamp(kSupplyBaseline + kSupplyCrowdingWeight * district.overpopulation +
        0.3 * district.weather_severity, 0.0, 1.0);
}

double target_corruption(const District& district) noexcept {
    const double pressure = desperation_index(district);
    const double policing_gap = std::max(0.0, 1.0 - district.security_presence);
    return std::clamp(kCorruptionPressure * pressure +
        kCorruptionSecurityWeight * policing_gap, 0.0, 1.0);
}

void evolve_inputs(District& district, double weather_severity) {
    district.weather_severity +=
        (weather_severity - district.weather_severity) * kWeatherReversion;

    const double crowd_target = target_overpopulation(district);
    district.overpopulation +=
        (crowd_target - district.overpopulation) * kOverpopulationReversion;

    const double supply_target = target_supply_shortage(district);
    district.supply_shortage +=
        (supply_target - district.supply_shortage) * (1.0 - kSupplyPersistence);

    const double corruption_target = target_corruption(district);
    const double rate = corruption_target > district.local_corruption
        ? kCorruptionRise : kCorruptionFall;
    district.local_corruption +=
        (corruption_target - district.local_corruption) * rate;
}

ScarState update_scars(District& district) {
    const double di = desperation_index(district);
    if (di >= kScarEnterDI) {
        ++district.days_above_critical;
        district.days_recovering = 0;
    } else {
        district.days_above_critical = 0;
        if (district.scar_active && di < kScarExitDI) {
            ++district.days_recovering;
        }
    }

    if (!district.scar_active) {
        if (district.days_above_critical > kScarDaysRequired) {
            district.scar_active = true;
        }
    } else if (district.days_recovering >= kScarRecoveryDays) {
        district.scar_active = false;
    }

    district.scar_intensity = std::clamp(
        district.scar_intensity + (district.scar_active ? kScarRiseRate : -kScarFallRate),
        0.0, 1.0);
    return {district.scar_active, district.scar_intensity,
        district.days_above_critical, di};
}

ScarState tick_day(District& district, double weather_severity) {
    evolve_inputs(district, weather_severity);
    return update_scars(district);
}

} // namespace simreality
