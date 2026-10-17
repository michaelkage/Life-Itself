#include "simreality/Trauma.h"

#include "simreality/Ecosystem.h"

#include <algorithm>
#include <cmath>

namespace simreality {
namespace {
double event_stress(ActionTag action_tag, bool was_victim) noexcept {
    switch (action_tag) {
    case ActionTag::CrimeArmedAssault: return was_victim ? 1.00 : 0.50;
    case ActionTag::CrimeAssault: return was_victim ? 0.60 : 0.30;
    case ActionTag::CrimeTheft: return was_victim ? 0.15 : 0.08;
    case ActionTag::CrimeVandalism: return was_victim ? 0.08 : 0.04;
    case ActionTag::InteractionPolite: return 0.0;
    }
    return 0.0;
}
}

double relieve(double days, double stress) noexcept {
    return stress * std::pow(kStressRetainedPerDay, days);
}

double absorb(NPC& npc, ActionTag action_tag, bool was_victim) noexcept {
    npc.personal_stress = std::min(
        1.0, npc.personal_stress + event_stress(action_tag, was_victim));
    return npc.personal_stress;
}

TraumaLevel personal_level(double stress) noexcept {
    if (stress >= kTierParanoidStress) return TraumaLevel::Paranoid;
    if (stress >= kTierAnxiousStress) return TraumaLevel::Anxious;
    return TraumaLevel::Baseline;
}

TraumaAssessment assess(const NPC& npc, double di) {
    const TraumaLevel from_person = personal_level(npc.personal_stress);
    const TraumaLevel from_world = distress_trauma(di).value_or(TraumaLevel::Baseline);
    const auto person_value = static_cast<int>(from_person);
    const auto world_value = static_cast<int>(from_world);
    const TraumaLevel level = person_value >= world_value ? from_person : from_world;
    const char* source = world_value > person_value ? "environment"
        : person_value > world_value ? "personal" : "both";
    return {level, npc.personal_stress, di, source};
}

TraumaAssessment daily_update(NPC& npc, double di, double days) {
    npc.personal_stress = relieve(days, npc.personal_stress);
    TraumaAssessment result = assess(npc, di);
    npc.trauma_level = result.level;
    return result;
}

} // namespace simreality
