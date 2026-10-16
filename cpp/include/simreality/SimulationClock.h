#pragma once

#include <cstdint>

namespace simreality {

// A deterministic simulation clock. It is independent of frame rate and Unreal.
struct ClockAdvance {
    double previous_hour{0.0};
    double current_hour{0.0};
    double elapsed_hours{0.0};
    std::uint64_t days_elapsed{0};
    std::uint64_t current_day{0};
    double hour_of_day{0.0};
};

class SimulationClock {
public:
    explicit SimulationClock(double initial_hour = 0.0);

    [[nodiscard]] double total_hours() const noexcept { return total_hours_; }
    [[nodiscard]] std::uint64_t day_index() const noexcept;
    [[nodiscard]] double hour_of_day() const noexcept;

    // Advances simulated time, not wall-clock time. Rejects negative, NaN,
    // infinite, or zero deltas so callers cannot silently stall or reverse time.
    ClockAdvance advance(double elapsed_hours);

private:
    double total_hours_{0.0};
};

} // namespace simreality
