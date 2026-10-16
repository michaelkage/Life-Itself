#include "simreality/CoreTypes.h"
#include "simreality/Decay.h"
#include "simreality/RandomStream.h"
#include "simreality/SimulationClock.h"
#include "simreality/SimulationRuntime.h"
#include "simreality/SimulationScheduler.h"

#include <cassert>
#include <cmath>
#include <stdexcept>

int main() {
    using namespace simreality;

    SimulationClock clock;
    SimulationScheduler scheduler;
    const auto first = clock.advance(23.5);
    const auto first_ticks = scheduler.collect(first);
    assert(first_ticks.size() == 23);
    assert(first_ticks.front().kind == TickKind::Hourly);
    assert(std::abs(first_ticks.front().at_hour - 1.0) < 1e-9);
    assert(std::abs(first_ticks.back().at_hour - 23.0) < 1e-9);

    const auto midnight = clock.advance(1.0);
    const auto midnight_ticks = scheduler.collect(midnight);
    assert(midnight_ticks.size() == 2);
    assert(midnight_ticks[0].kind == TickKind::Hourly);
    assert(midnight_ticks[1].kind == TickKind::Daily);
    assert(std::abs(midnight_ticks[0].at_hour - 24.0) < 1e-9);
    assert(std::abs(midnight_ticks[1].at_hour - 24.0) < 1e-9);

    const auto multi_day = clock.advance(48.0);
    const auto multi_day_ticks = scheduler.collect(multi_day);
    assert(multi_day_ticks.size() == 50); // 48 hourly + daily at 48 and 72.
    assert(multi_day.days_elapsed == 2);
    assert(multi_day.current_day == 3);

    bool rejected_zero = false;
    try {
        (void)clock.advance(0.0);
    } catch (const std::invalid_argument&) {
        rejected_zero = true;
    }
    assert(rejected_zero);

    NPCMemory memory;
    memory.witness_id = "witness-1";
    memory.target_entity_id = "target-1";
    memory.retention = 0.9;
    assert(memory.is_actionable());
    memory.retention = 0.5;
    assert(!memory.is_actionable());
    memory.retention = 0.9;
    memory.target_entity_id.clear();
    assert(!memory.is_actionable());

    RandomStream rng_a(12345U);
    RandomStream rng_b(12345U);
    for (int i = 0; i < 100; ++i) {
        assert(rng_a.next_u64() == rng_b.next_u64());
    }

    RandomStream bounded_rng(42U);
    for (int i = 0; i < 1000; ++i) {
        assert(bounded_rng.bounded(7U) < 7U);
    }
    bool rejected_empty_range = false;
    try {
        (void)bounded_rng.bounded(0U);
    } catch (const std::invalid_argument&) {
        rejected_empty_range = true;
    }
    assert(rejected_empty_range);

    SimulationRuntime runtime;
    const auto runtime_ticks = runtime.advance(24.0);
    assert(runtime_ticks.size() == 25);
    assert(runtime_ticks[23].kind == TickKind::Hourly);
    assert(runtime_ticks[24].kind == TickKind::Daily);
    assert(std::abs(runtime.total_hours() - 24.0) < 1e-9);

    NPCMemory theft;
    theft.witness_id = "witness";
    theft.target_entity_id = "target";
    theft.initial_impact = 1.0;
    theft.retention = 1.0;
    theft.timestamp_hour = 12.0;
    theft.action_tag = ActionTag::CrimeTheft;
    const double theft_after_day = retention_after(theft, AgeBand::Adult, 36.0, Weather::Clear);
    assert(theft_after_day < 0.6);
    assert(theft_after_day >= 0.0);

    NPCMemory armed = theft;
    armed.action_tag = ActionTag::CrimeArmedAssault;
    const double armed_after_year = retention_after(
        armed, AgeBand::YoungAdult, 12.0 + 24.0 * 365.0, Weather::Clear);
    assert(std::abs(armed_after_year - 0.85) < 0.01);

    assert(decay_constant(AgeBand::YoungAdult, ActionTag::CrimeTheft, 12.0, Weather::Clear) >= 0.0);
    assert(visibility_modifier(12.0, Weather::Clear) < visibility_modifier(0.0, Weather::Rain));

    const auto decayed = sweep({theft}, AgeBand::Adult, 36.0, Weather::Clear);
    assert(decayed.size() == 1);
    assert(decayed[0].retention < theft.retention);

    return 0;
}
