#pragma once

#include "simreality/CoreTypes.h"

#include <optional>
#include <string>
#include <vector>

namespace simreality {

enum class IllegalBranch { Shoplift, CargoHijack, BribeOfficial, ExtortNeighbour, JoinSyndicate };

struct BehaviourDecision {
    bool illegal{false};
    std::optional<IllegalBranch> branch{};
    double desperation_index{0.0};
    double moral_shackle{0.0};

    [[nodiscard]] std::string reason() const;
};

[[nodiscard]] double desperation_index(const District& district) noexcept;
[[nodiscard]] BehaviourDecision evaluate(const NPC& npc, const District& district);
[[nodiscard]] BehaviourDecision apply_district_pressure(NPC& resident, const District& district);
[[nodiscard]] std::optional<TraumaLevel> distress_trauma(double di) noexcept;

// Recomputes each resident's DI and behaviour for the current district day.
// Residents are passed explicitly so WorldState can own NPCs without duplicating them.
[[nodiscard]] std::vector<BehaviourDecision> apply_district_pressure(
    std::vector<NPC>& residents, const District& district);

[[nodiscard]] const char* illegal_branch_name(IllegalBranch branch) noexcept;

} // namespace simreality
