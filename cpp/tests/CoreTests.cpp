#include "simreality/CoreTypes.h"
#include "simreality/SimulationClock.h"

#include <cassert>
#include <cmath>
#include <stdexcept>

int main() {
    using namespace simreality;

    SimulationClock clock;
    const auto first = clock.advance(23.5);
    assert(first.days_elapsed == 0);
    assert(std::abs(first.hour_of_day - 23.5) < 1e-9);

    const auto midnight = clock.advance(1.0);
    assert(midnight.days_elapsed == 1);
    assert(midnight.current_day == 1);
    assert(std::abs(midnight.hour_of_day - 0.5) < 1e-9);

    const auto multi_day = clock.advance(48.0);
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

    return 0;
}
