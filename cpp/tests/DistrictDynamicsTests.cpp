#include "simreality/DistrictDynamics.h"
#include <cassert>
#include <cmath>
int main() {
    using namespace simreality;
    District calm;
    calm.overpopulation = 0.0; calm.supply_shortage = 0.0;
    calm.weather_severity = 0.0; calm.local_corruption = 0.0;
    assert(std::abs(desperation_index(calm)) < 1e-12);
    District crisis;
    crisis.overpopulation = 1.0; crisis.supply_shortage = 1.0;
    crisis.weather_severity = 1.0; crisis.local_corruption = 1.0;
    assert(std::abs(desperation_index(crisis) - 1.0) < 1e-12);
    District evolving;
    evolving.population = 90; evolving.capacity = 100;
    const double before = evolving.overpopulation;
    evolve_inputs(evolving, 1.0);
    assert(evolving.overpopulation > before);
    assert(evolving.weather_severity > 0.0);
    assert(evolving.supply_shortage > 0.0);
    District scarred;
    scarred.overpopulation = 1.0; scarred.supply_shortage = 1.0;
    scarred.weather_severity = 1.0; scarred.local_corruption = 1.0;
    for (int day = 0; day < 3; ++day) assert(!update_scars(scarred).active);
    assert(update_scars(scarred).active);
    scarred.overpopulation = 0.0; scarred.supply_shortage = 0.0;
    scarred.weather_severity = 0.0; scarred.local_corruption = 0.0;
    for (int day = 0; day < 4; ++day) (void)update_scars(scarred);
    assert(!scarred.scar_active);
    return 0;
}
