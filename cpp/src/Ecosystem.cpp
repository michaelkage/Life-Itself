#include "simreality/Ecosystem.h"

#include <algorithm>
#include <sstream>

namespace simreality {
namespace {
constexpr double kOverpopulationWeight = 1.2;
constexpr double kSupplyShortageWeight = 1.5;
constexpr double kWeatherWeight = 0.8;
constexpr double kCorruptionWeight = 1.1;
constexpr double kWeightTotal = kOverpopulationWeight + kSupplyShortageWeight +
    kWeatherWeight + kCorruptionWeight;
}

double desperation_index(const District& district) noexcept {
    const double raw = district.overpopulation * kOverpopulationWeight +
        district.supply_shortage * kSupplyShortageWeight +
        district.weather_severity * kWeatherWeight +
        district.local_corruption * kCorruptionWeight;
    return std::clamp(raw / kWeightTotal, 0.0, 1.0);
}

const char* illegal_branch_name(IllegalBranch branch) noexcept {
    switch (branch) {
    case IllegalBranch::Shoplift: return "Shoplift";
    case IllegalBranch::CargoHijack: return "CargoHijack";
    case IllegalBranch::BribeOfficial: return "BribeOfficial";
    case IllegalBranch::ExtortNeighbour: return "ExtortNeighbour";
    case IllegalBranch::JoinSyndicate: return "JoinSyndicate";
    }
    return "Unknown";
}

std::string BehaviourDecision::reason() const {
    std::ostringstream out;
    out.setf(std::ios::fixed);
    out.precision(2);
    if (!illegal) {
        out << "DI " << desperation_index << " <= shackle " << moral_shackle;
    } else {
        out << "DI " << desperation_index << " > shackle " << moral_shackle
            << " -> " << illegal_branch_name(branch.value_or(IllegalBranch::ExtortNeighbour));
    }
    return out.str();
}

BehaviourDecision evaluate(const NPC& npc, const District& district) {
    const double di = desperation_index(district);
    if (di <= npc.moral_shackle) {
        return {false, std::nullopt, di, npc.moral_shackle};
    }

    IllegalBranch branch;
    if (district.supply_shortage >= 0.6 && district.security_presence <= 0.4) {
        branch = district.supply_shortage >= 0.8
            ? IllegalBranch::CargoHijack : IllegalBranch::Shoplift;
    } else if (district.local_corruption >= 0.5 && district.overpopulation >= 0.5) {
        branch = district.overpopulation >= 0.75
            ? IllegalBranch::JoinSyndicate : IllegalBranch::BribeOfficial;
    } else {
        branch = IllegalBranch::ExtortNeighbour;
    }
    return {true, branch, di, npc.moral_shackle};
}

std::optional<TraumaLevel> distress_trauma(double di) noexcept {
    if (di >= 0.90) return TraumaLevel::Vigilante;
    if (di >= 0.75) return TraumaLevel::Paranoid;
    if (di >= 0.60) return TraumaLevel::Anxious;
    return std::nullopt;
}

BehaviourDecision apply_district_pressure(NPC& npc, const District& district) {
    const double di = desperation_index(district);
    npc.desperation_index = di;
    BehaviourDecision decision = evaluate(npc, district);
    if (decision.illegal) {
        const auto tier = distress_trauma(di);
        if (tier && static_cast<int>(*tier) > static_cast<int>(npc.trauma_level)) {
            npc.trauma_level = *tier;
        }
    }
    return decision;
}

std::vector<BehaviourDecision> apply_district_pressure(
    std::vector<NPC>& residents, const District& district) {
    std::vector<BehaviourDecision> results;
    results.reserve(residents.size());
    for (NPC& npc : residents) {
        results.push_back(apply_district_pressure(npc, district));
    }
    return results;
}

} // namespace simreality
