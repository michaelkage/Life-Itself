#pragma once

#include "simreality/SimulationClock.h"
#include "simreality/SimulationScheduler.h"

#include <vector>

namespace simreality {

struct DualClockAdvance {
    double previous_real_seconds{0.0};
    double current_real_seconds{0.0};
    double elapsed_real_seconds{0.0};
    double elapsed_simulation_hours{0.0};
    std::vector<ScheduledTick> simulation_ticks{};
};

// Small orchestration boundary for time-based systems.
// Domain systems will be connected here after their C++ ports have parity tests.
class SimulationRuntime {
public:
    explicit SimulationRuntime(double initial_hour = 0.0);

    [[nodiscard]] double total_hours() const noexcept { return clock_.total_hours(); }
    [[nodiscard]] double real_time_seconds() const noexcept { return real_time_seconds_; }
    [[nodiscard]] std::uint64_t day_index() const noexcept { return clock_.day_index(); }
    [[nodiscard]] double hour_of_day() const noexcept { return clock_.hour_of_day(); }

    // Advances the clock and returns every due tick in chronological order.
    // The caller is responsible for dispatching each tick to domain systems.
    [[nodiscard]] std::vector<ScheduledTick> advance(double elapsed_hours);

    // Advance from a host-frame delta. A zero rate pauses simulation time while
    // wall time continues; a positive rate is measured in sim-hours per real second.
    [[nodiscard]] DualClockAdvance advance_frame(
        double elapsed_real_seconds, double simulation_hours_per_real_second);

private:
    SimulationClock clock_;
    SimulationScheduler scheduler_;
    double real_time_seconds_{0.0};
};

} // namespace simreality
