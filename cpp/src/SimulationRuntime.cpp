#include "simreality/SimulationRuntime.h"

namespace simreality {

SimulationRuntime::SimulationRuntime(double initial_hour)
    : clock_(initial_hour), scheduler_(initial_hour) {}

std::vector<ScheduledTick> SimulationRuntime::advance(double elapsed_hours) {
    const ClockAdvance clock_advance = clock_.advance(elapsed_hours);
    return scheduler_.collect(clock_advance);
}

} // namespace simreality
