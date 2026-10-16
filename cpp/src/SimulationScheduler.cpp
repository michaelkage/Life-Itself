#include "simreality/SimulationScheduler.h"

#include <cmath>
#include <stdexcept>

namespace simreality {
namespace {
constexpr double kHoursPerDay = 24.0;
constexpr double kEpsilon = 1e-9;
}

SimulationScheduler::SimulationScheduler(double initial_hour) {
    if (!std::isfinite(initial_hour) || initial_hour < 0.0) {
        throw std::invalid_argument("initial simulation hour must be finite and non-negative");
    }
    next_hourly_hour_ = (std::floor(initial_hour) + 1.0);
    next_daily_hour_ = (std::floor(initial_hour / kHoursPerDay) + 1.0) * kHoursPerDay;
}

std::vector<ScheduledTick> SimulationScheduler::collect(const ClockAdvance& advance) {
    if (!std::isfinite(advance.previous_hour) || !std::isfinite(advance.current_hour) ||
        advance.current_hour < advance.previous_hour) {
        throw std::invalid_argument("clock advance must be finite and non-reversing");
    }

    std::vector<ScheduledTick> ticks;
    while (next_hourly_hour_ <= advance.current_hour + kEpsilon ||
           next_daily_hour_ <= advance.current_hour + kEpsilon) {
        if (next_hourly_hour_ <= next_daily_hour_ + kEpsilon &&
            next_hourly_hour_ <= advance.current_hour + kEpsilon) {
            // Avoid reporting a tick that belongs to before this advance.
            if (next_hourly_hour_ > advance.previous_hour + kEpsilon) {
                const auto day = static_cast<std::uint64_t>(
                    std::floor(next_hourly_hour_ / kHoursPerDay));
                ticks.push_back({TickKind::Hourly, next_hourly_hour_, day});
            }
            next_hourly_hour_ += 1.0;
        } else if (next_daily_hour_ <= advance.current_hour + kEpsilon) {
            if (next_daily_hour_ > advance.previous_hour + kEpsilon) {
                const auto day = static_cast<std::uint64_t>(
                    std::floor(next_daily_hour_ / kHoursPerDay));
                ticks.push_back({TickKind::Daily, next_daily_hour_, day});
            }
            next_daily_hour_ += kHoursPerDay;
        }
    }
    return ticks;
}

} // namespace simreality
