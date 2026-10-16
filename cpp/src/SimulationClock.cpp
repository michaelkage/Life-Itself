#include "simreality/SimulationClock.h"

#include <cmath>
#include <stdexcept>

namespace simreality {
namespace {
constexpr double kHoursPerDay = 24.0;
}

SimulationClock::SimulationClock(double initial_hour) : total_hours_(initial_hour) {
    if (!std::isfinite(initial_hour) || initial_hour < 0.0) {
        throw std::invalid_argument("initial simulation hour must be finite and non-negative");
    }
}

std::uint64_t SimulationClock::day_index() const noexcept {
    return static_cast<std::uint64_t>(std::floor(total_hours_ / kHoursPerDay));
}

double SimulationClock::hour_of_day() const noexcept {
    return std::fmod(total_hours_, kHoursPerDay);
}

ClockAdvance SimulationClock::advance(double elapsed_hours) {
    if (!std::isfinite(elapsed_hours) || elapsed_hours <= 0.0) {
        throw std::invalid_argument("elapsed simulation hours must be finite and positive");
    }

    const double previous = total_hours_;
    const std::uint64_t previous_day = day_index();
    total_hours_ += elapsed_hours;

    if (!std::isfinite(total_hours_)) {
        total_hours_ = previous;
        throw std::overflow_error("simulation clock overflow");
    }

    const std::uint64_t new_day = day_index();
    return ClockAdvance{
        previous,
        total_hours_,
        elapsed_hours,
        new_day - previous_day,
        new_day,
        hour_of_day()
    };
}

} // namespace simreality
