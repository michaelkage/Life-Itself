#include "simreality/Decay.h"

#include <algorithm>
#include <cmath>

namespace simreality {
namespace {

double age_multiplier(AgeBand age_band) noexcept {
    switch (age_band) {
    case AgeBand::YoungAdult: return 1.0;
    case AgeBand::Adult: return 1.2;
    case AgeBand::Senior: return 1.4;
    }
    return 1.0;
}

double decay_rate_multiplier(ActionTag action_tag) noexcept {
    switch (action_tag) {
    case ActionTag::InteractionPolite: return 4.0;
    case ActionTag::CrimeVandalism: return 2.5;
    case ActionTag::CrimeTheft: return 2.0;
    case ActionTag::CrimeAssault: return 0.4;
    case ActionTag::CrimeArmedAssault: return 0.05;
    }
    return 1.0;
}

double retention_floor(ActionTag action_tag) noexcept {
    switch (action_tag) {
    case ActionTag::InteractionPolite: return 0.0;
    case ActionTag::CrimeVandalism: return 0.0;
    case ActionTag::CrimeTheft: return 0.0;
    case ActionTag::CrimeAssault: return 0.4;
    case ActionTag::CrimeArmedAssault: return 0.85;
    }
    return 0.0;
}

} // namespace

double visibility_modifier(double game_hour, Weather weather) noexcept {
    const double day_factor = (game_hour >= 6.0 && game_hour < 18.0) ? 0.8 : 1.5;
    const double weather_factor = (weather == Weather::Clear) ? 1.0 : 2.5;
    return day_factor * weather_factor;
}

double decay_constant(
    AgeBand age_band,
    ActionTag action_tag,
    double game_hour,
    Weather weather,
    std::optional<double> lambda_base) noexcept {
    const double base = lambda_base.value_or(kLambdaBase);
    return base * age_multiplier(age_band) *
        visibility_modifier(game_hour, weather) * decay_rate_multiplier(action_tag);
}

double retention_after(
    const NPCMemory& memory,
    AgeBand age_band,
    double current_hour,
    Weather weather,
    std::optional<double> lambda_base) noexcept {
    if (memory.timestamp_hour > current_hour) {
        return memory.initial_impact;
    }

    const double rate = decay_constant(
        age_band, memory.action_tag, memory.timestamp_hour, weather, lambda_base);
    const double elapsed = current_hour - memory.timestamp_hour;
    const double floor = retention_floor(memory.action_tag);
    const double retention = memory.initial_impact *
        (floor + (1.0 - floor) * std::exp(-rate * elapsed));
    return std::clamp(retention, 0.0, 1.0);
}

std::vector<NPCMemory> sweep(
    const std::vector<NPCMemory>& memories,
    AgeBand age_band,
    double current_hour,
    Weather weather,
    std::optional<double> lambda_base) {
    std::vector<NPCMemory> updated = memories;
    for (auto& memory : updated) {
        memory.retention = retention_after(memory, age_band, current_hour, weather, lambda_base);
    }
    return updated;
}

} // namespace simreality
