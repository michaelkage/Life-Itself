#include "simreality/DistrictDynamics.h"
#include "simreality/Fixers.h"
#include "simreality/Gossip.h"
#include "simreality/Justice.h"
#include "simreality/Reputation.h"
#include "simreality/Trauma.h"

#include <iomanip>
#include <iostream>
#include <vector>

int main() {
    using namespace simreality;
    std::cout << std::setprecision(17);

    NPCMemory memory;
    memory.witness_id = "witness";
    memory.target_entity_id = "target";
    memory.retention = 0.8;
    memory.initial_impact = 0.8;
    memory.action_tag = ActionTag::CrimeTheft;
    memory.description.height_m = 1.82;
    memory.description.height_uncertainty_m = 0.2;
    memory.description.jacket_colour_weights = {{"black", 0.8}, {"blue", 0.2}};
    memory.description.observations = 2;
    const auto rumour = retell(memory);
    if (!rumour) return 2;
    Rumour second = *rumour;
    second.description.height_m = 1.78;
    second.description.jacket_colour_weights = {{"black", 0.5}, {"red", 0.5}};
    second.retention = 0.6;
    const auto merged = corroborate(*rumour, second);
    std::cout << "gossip " << rumour->retention << ' ' << rumour->is_attributable()
              << ' ' << merged.retention << ' ' << merged.description.observations
              << ' ' << jacket_confidence(merged.description) << '\n';

    District district;
    district.district_id = "D";
    district.overpopulation = 0.55;
    district.supply_shortage = 0.4;
    district.weather_severity = 0.2;
    district.local_corruption = 0.3;
    district.security_presence = 0.25;
    district.population = 80;
    district.capacity = 100;
    const auto scar = tick_day(district, 0.9);
    std::cout << "district " << district.overpopulation << ' ' << district.supply_shortage
              << ' ' << district.weather_severity << ' ' << district.local_corruption
              << ' ' << scar.desperation_index << ' ' << scar.intensity << ' '
              << scar.active << '\n';

    NPC person;
    person.entity_id = "person";
    const double stress = absorb(person, ActionTag::CrimeTheft, true);
    std::cout << "trauma " << stress << ' ' << relieve(3.0, stress) << ' '
              << static_cast<int>(personal_level(stress)) << ' '
              << static_cast<int>(assess(person, 0.9).level) << '\n';

    const Charge charge = charge_from_memory(memory);
    std::cout << "justice " << charge.severity() << ' ' << charge.sentence() << ' '
              << charge.provable() << ' ' << enforcement_probability(ActionTag::CrimeTheft, 0.9)
              << '\n';

    const auto profile = local_reputation(std::vector<NPCMemory>{memory}, "target");
    std::cout << "reputation " << profile.reputation << ' ' << profile.accusation_penalty
              << ' ' << profile.record_penalty << '\n';

    District pressured;
    pressured.district_id = "D";
    pressured.overpopulation = 1.0;
    pressured.supply_shortage = 1.0;
    pressured.weather_severity = 1.0;
    pressured.local_corruption = 1.0;
    pressured.security_presence = 0.0;
    FixerProfile fixer;
    fixer.entity_id = "fixer";
    fixer.district_id = "D";
    fixer.standing = 0.3;
    fixer.warrants = 0.2;
    const double probability = betrayal_probability(desperation_index(pressured), 0.8, fixer.warrants, fixer.standing);
    const auto negotiation = negotiate(fixer, pressured, 0.8, 0.8, 0.1);
    std::cout << "fixer " << probability << ' ' << negotiation.accepted << ' '
              << negotiation.bribe_paid << ' ' << negotiation.betrayed << ' '
              << fixer.bribes_accepted << '\n';
}
