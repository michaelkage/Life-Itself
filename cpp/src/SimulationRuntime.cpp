#include "simreality/SimulationRuntime.h"

#include <cmath>
#include <stdexcept>
#include <utility>

namespace simreality {

SimulationRuntime::SimulationRuntime(
    double initial_hour, double initial_real_time_seconds)
    : clock_(initial_hour), scheduler_(initial_hour),
      real_time_seconds_(initial_real_time_seconds) {
    if (!std::isfinite(initial_real_time_seconds) || initial_real_time_seconds < 0.0) {
        throw std::invalid_argument(
            "initial real-time seconds must be finite and non-negative");
    }
}

std::vector<ScheduledTick> SimulationRuntime::advance(double elapsed_hours) {
    const ClockAdvance clock_advance = clock_.advance(elapsed_hours);
    return scheduler_.collect(clock_advance);
}

DualClockAdvance SimulationRuntime::advance_frame(
    double elapsed_real_seconds, double simulation_hours_per_real_second) {
    if (!std::isfinite(elapsed_real_seconds) || elapsed_real_seconds < 0.0) {
        throw std::invalid_argument("elapsed real seconds must be finite and non-negative");
    }
    if (!std::isfinite(simulation_hours_per_real_second)
        || simulation_hours_per_real_second < 0.0) {
        throw std::invalid_argument(
            "simulation rate must be finite and non-negative");
    }
    const double next_real_seconds = real_time_seconds_ + elapsed_real_seconds;
    if (!std::isfinite(next_real_seconds)) {
        throw std::overflow_error("real-time clock overflow");
    }
    const double elapsed_simulation_hours =
        elapsed_real_seconds * simulation_hours_per_real_second;
    if (!std::isfinite(elapsed_simulation_hours)) {
        throw std::overflow_error("simulation-time frame delta overflow");
    }

    std::vector<ScheduledTick> ticks;
    if (elapsed_simulation_hours > 0.0) {
        ticks = advance(elapsed_simulation_hours);
    }

    const double previous_real_seconds = real_time_seconds_;
    real_time_seconds_ = next_real_seconds;
    return DualClockAdvance{
        previous_real_seconds,
        real_time_seconds_,
        elapsed_real_seconds,
        elapsed_simulation_hours,
        std::move(ticks),
    };
}

} // namespace simreality
