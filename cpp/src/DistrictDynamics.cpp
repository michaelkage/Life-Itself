#include "simreality/DistrictDynamics.h"

#include <algorithm>

namespace simreality {
namespace {
double clamp01(double value) noexcept { return std::clamp(value, 0.0, 1.0); }
}

double desperation_index(const District& d) noexcept {
    const double raw = d.overpopulation * 1.2 + d.supply_shortage * 1.5 +
        d.weather_severity * 0.8 + d.local_corruption * 1.1;
    return clamp01(raw / 4.6);
}

double target_overpopulation(const District& d) noexcept {
    if (d.capacity == 0) return 1.0;
    return clamp01(static_cast<double>(d.population) / static_cast<double>(d.capacity));
}

double target_supply_shortage(const District& d) noexcept {
    return clamp01(kSupplyBaseline + kSupplyCrowdingWeight * d.overpopulation +
        0.3 * d.weather_severity);
}

double target_corruption(const District& d) noexcept {
    const double pressure = desperation_index(d);
    const double policing_gap = std::max(0.0, 1.0 - d.security_presence);
    return clamp01(kCorruptionPressure * pressure + kCorruptionSecurityWeight * policing_gap);
}

void evolve_inputs(District& d, double weather_severity) {
    const double weather = clamp01(weather_severity);
    d.weather_severity += (weather - d.weather_severity) * kWeatherReversion;

    const double crowd_target = target_overpopulation(d);
    d.overpopulation += (crowd_target - d.overpopulation) * kOverpopulationReversion;

    const double supply_target = target_supply_shortage(d);
    d.supply_shortage += (supply_target - d.supply_shortage) * (1.0 - kSupplyPersistence);

    const double corruption_target = target_corruption(d);
    const double rate = corruption_target > d.local_corruption ? kCorruptionRise : kCorruptionFall;
    d.local_corruption += (corruption_target - d.local_corruption) * rate;

    d.overpopulation = clamp01(d.overpopulation);
    d.supply_shortage = clamp01(d.supply_shortage);
    d.weather_severity = clamp01(d.weather_severity);
    d.local_corruption = clamp01(d.local_corruption);
}

ScarState update_scars(District& d) noexcept {
    const double di = desperation_index(d);
    if (di >= kScarEnterDI) {
        ++d.days_above_critical;
        d.days_recovering = 0;
    } else {
        d.days_above_critical = 0;
        if (d.scar_active && di < kScarExitDI) ++d.days_recovering;
    }

    // Match the Python reference: the trigger is strictly greater than 3.
    if (!d.scar_active) {
        if (d.days_above_critical > kScarDaysRequired) d.scar_active = true;
    } else if (d.days_recovering >= kScarRecoveryDays) {
        d.scar_active = false;
    }

    d.scar_intensity = clamp01(d.scar_intensity +
        (d.scar_active ? kScarRiseRate : -kScarFallRate));
    return ScarState{d.scar_active, d.scar_intensity, d.days_above_critical, di};
}

ScarState tick_day(District& d, double weather_severity) {
    evolve_inputs(d, weather_severity);
    return update_scars(d);
}

} // namespace simreality
