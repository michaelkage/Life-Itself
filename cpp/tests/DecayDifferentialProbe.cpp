#include "simreality/Decay.h"

#include <iomanip>
#include <iostream>

int main() {
    using namespace simreality;
    struct Case {
        AgeBand age;
        ActionTag action;
        double formed;
        double now;
        Weather weather;
    };
    const Case cases[] = {
        {AgeBand::YoungAdult, ActionTag::CrimeTheft, 12.0, 36.0, Weather::Clear},
        {AgeBand::Adult, ActionTag::CrimeArmedAssault, 0.0, 8760.0, Weather::Clear},
        {AgeBand::Senior, ActionTag::CrimeAssault, 22.0, 70.0, Weather::HeavyRain},
        {AgeBand::Adult, ActionTag::InteractionPolite, 6.0, 18.0, Weather::Clear},
        {AgeBand::YoungAdult, ActionTag::CrimeVandalism, 23.0, 47.0, Weather::HeavyRain},
    };
    std::cout << std::setprecision(17);
    for (const auto& test : cases) {
        NPCMemory memory;
        memory.initial_impact = 0.73;
        memory.retention = 0.73;
        memory.timestamp_hour = test.formed;
        memory.action_tag = test.action;
        std::cout << retention_after(memory, test.age, test.now, test.weather) << '\n';
    }
}
