#pragma once

#include "simreality/SimulationClock.h"
#include "simreality/SimulationScheduler.h"

#include <vector>

namespace simreality {

// Small orchestration boundary for time-based systems.
// Domain systems will be connected here after their C++ ports have parity tests.
class SimulationRuntime {
public:
    explicit SimulationRuntime(double initial_hour = 0.0);

    [[nodiscard]] double total_hours() const noexcept { return clock_.total_hours(); }
    [[nodiscard]] std::uint64_t day_index() const noexcept { return clock_.day_index(); }
    [[nodiscard]] double hour_of_day() const noexcept { return clock_.hour_of_day(); }

    // Advances the clock and returns every due tick in chronological order.
    // The caller is responsible for dispatching each tick to domain systems.
    [[nodiscard]] std::vector<ScheduledTick> advance(double elapsed_hours);

private:
    SimulationClock clock_;
    SimulationScheduler scheduler_;
};

} // namespace simreality
