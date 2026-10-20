#pragma once

#include "simreality/CoreTypes.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace simreality {

enum class LifeStatus : std::uint8_t { Active, Spectator, Ghost, Archived };

struct MedicalCondition {
    std::string condition_id{};
    double severity{0.0};
    double recovery_per_day{0.05};
    double work_capacity_at_full_severity{0.25};
    bool lasting_impairment{false};
    double impairment_floor{0.0};
    double care_hours_per_severity{4.0};
};

struct MedicalTreatment {
    std::string treatment_id{};
    std::string condition_id{};
    double effectiveness{0.0};
    double daily_cost{0.0};
    double complication_risk{0.0};
    bool active{true};
};

struct RecoveryRange {
    double expected{0.0};
    double lower{0.0};
    double upper{0.0};
    double complication_risk{0.0};
};

struct LifeCharacter {
    EntityId entity_id{};
    LifeStatus status{LifeStatus::Active};
    std::uint64_t death_day{0};
    std::string death_cause{};
    std::vector<MedicalCondition> conditions{};
    std::vector<MedicalTreatment> treatments{};
    double care_need_hours{0.0};
    double lost_income{0.0};
    std::uint32_t missed_work_days{0};
    std::map<EntityId, double> personality{};
    std::map<EntityId, double> memories{};
};

struct LifeObligation {
    std::string obligation_id{};
    EntityId debtor_id{};
    EntityId creditor_id{};
    double amount_due{0.0};
    std::uint64_t due_day{0};
    bool settled{false};
    bool missed{false};
};

struct GhostTimeWindow {
    double start_hour{0.0};
    double end_hour{0.0};
    double strength{1.0};
};

struct GhostInfluenceResult {
    bool accepted{false};
    double score{0.0};
    std::string reason{};
};

// Lives, care, obligations and ghost decisions are owned by the world coordinator.
// The coordinator uses the existing NPC memory, relationship and economic state.
class LifeCoordinator {
public:
    void register_character(const EntityId& id);
    void add_condition(const EntityId& id, MedicalCondition condition);
    void add_treatment(const EntityId& id, MedicalTreatment treatment);
    void add_obligation(LifeObligation obligation);
    void set_ghost_windows(std::vector<GhostTimeWindow> windows);
    [[nodiscard]] bool kill(const EntityId& id, std::uint64_t day, std::string cause);
    [[nodiscard]] bool enter_ghost(const EntityId& id);
    [[nodiscard]] GhostInfluenceResult attempt_ghost_influence(
        const EntityId& ghost_id, const EntityId& npc_id, const std::string& action,
        double hour_of_day, const WorldState& state, std::uint64_t random_sample) const;
    void advance_day(WorldState& state, std::uint64_t day);
    [[nodiscard]] const std::map<EntityId, LifeCharacter>& characters() const noexcept {
        return characters_;
    }
    [[nodiscard]] const std::vector<LifeObligation>& obligations() const noexcept {
        return obligations_;
    }
    [[nodiscard]] RecoveryRange estimate_recovery(
        const EntityId& id, const std::string& condition_id) const;

private:
    [[nodiscard]] LifeCharacter& find_character(const EntityId& id);
    [[nodiscard]] const LifeCharacter& find_character(const EntityId& id) const;
    std::map<EntityId, LifeCharacter> characters_{};
    std::vector<LifeObligation> obligations_{};
    std::vector<GhostTimeWindow> ghost_windows_{};
};

} // namespace simreality
