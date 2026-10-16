#pragma once

#include "simreality/SimulationClock.h"

#include <cstdint>
#include <vector>

namespace simreality {

enum class TickKind { Hourly, Daily };

struct ScheduledTick {
    TickKind kind{TickKind::Hourly};
    double at_hour{0.0};
    std::uint64_t day_index{0};
};

// Converts clock advances into stable simulation work items.
// At an exact day boundary, Hourly is emitted before Daily.
class SimulationScheduler {
public:
    explicit SimulationScheduler(double initial_hour = 0.0);

    [[nodiscard]] std::vector<ScheduledTick> collect(const ClockAdvance& advance);

private:
    double next_hourly_hour_{1.0};
    double next_daily_hour_{24.0};
};

} // namespace simreality
