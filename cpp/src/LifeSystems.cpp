#include "simreality/LifeSystems.h"

#include <cmath>
#include <functional>
#include <stdexcept>

namespace simreality {
namespace {
double clamp01(double value) { return std::clamp(value, 0.0, 1.0); }

const NPC* find_npc(const WorldState& state, const EntityId& id) {
    for (const NPC& npc : state.npcs) if (npc.entity_id == id) return &npc;
    return nullptr;
}
NPC* find_npc(WorldState& state, const EntityId& id) {
    for (NPC& npc : state.npcs) if (npc.entity_id == id) return &npc;
    return nullptr;
}
} // namespace

LifeCharacter& LifeCoordinator::find_character(const EntityId& id) {
    const auto found = characters_.find(id);
    if (found == characters_.end()) throw std::out_of_range("life character not found: " + id);
    return found->second;
}
const LifeCharacter& LifeCoordinator::find_character(const EntityId& id) const {
    const auto found = characters_.find(id);
    if (found == characters_.end()) throw std::out_of_range("life character not found: " + id);
    return found->second;
}

void LifeCoordinator::restore_snapshot(
    std::map<EntityId, LifeCharacter> characters,
    std::vector<LifeObligation> obligations,
    std::vector<GhostTimeWindow> ghost_windows) {
    for (const auto& [id, character] : characters) {
        if (id.empty() || character.entity_id != id
            || static_cast<std::uint8_t>(character.status) > static_cast<std::uint8_t>(LifeStatus::Archived))
            throw std::invalid_argument("invalid lifecycle character snapshot");
        for (const MedicalCondition& condition : character.conditions) {
            if (condition.condition_id.empty() || !std::isfinite(condition.severity)
                || condition.severity < 0.0 || condition.severity > 1.0
                || !std::isfinite(condition.recovery_per_day) || condition.recovery_per_day < 0.0
                || !std::isfinite(condition.impairment_floor) || condition.impairment_floor < 0.0
                || condition.impairment_floor > 1.0)
                throw std::invalid_argument("invalid medical condition snapshot");
        }
    }
    for (const LifeObligation& obligation : obligations) {
        if (obligation.obligation_id.empty() || !std::isfinite(obligation.amount_due)
            || obligation.amount_due < 0.0)
            throw std::invalid_argument("invalid obligation snapshot");
    }
    for (const GhostTimeWindow& window : ghost_windows) {
        if (!std::isfinite(window.start_hour) || !std::isfinite(window.end_hour)
            || !std::isfinite(window.strength) || window.start_hour < 0.0
            || window.end_hour > 24.0 || window.start_hour >= window.end_hour
            || window.strength < 0.0)
            throw std::invalid_argument("invalid ghost window snapshot");
    }
    characters_ = std::move(characters);
    obligations_ = std::move(obligations);
    ghost_windows_ = std::move(ghost_windows);
}

void LifeCoordinator::register_character(const EntityId& id) {
    if (id.empty()) throw std::invalid_argument("character id cannot be empty");
    characters_.try_emplace(id, LifeCharacter{.entity_id = id});
}

void LifeCoordinator::add_condition(const EntityId& id, MedicalCondition condition) {
    if (!std::isfinite(condition.severity) || !std::isfinite(condition.recovery_per_day)
        || condition.severity < 0.0 || condition.severity > 1.0 || condition.recovery_per_day < 0.0) {
        throw std::invalid_argument("invalid medical condition severity or recovery");
    }
    LifeCharacter& character = find_character(id);
    for (const MedicalCondition& existing : character.conditions)
        if (existing.condition_id == condition.condition_id)
            throw std::invalid_argument("duplicate medical condition id");
    character.conditions.push_back(std::move(condition));
}

void LifeCoordinator::add_treatment(const EntityId& id, MedicalTreatment treatment) {
    LifeCharacter& character = find_character(id);
    const auto condition = std::find_if(character.conditions.begin(), character.conditions.end(),
        [&treatment](const MedicalCondition& value) { return value.condition_id == treatment.condition_id; });
    if (condition == character.conditions.end()) throw std::out_of_range("treatment condition not found");
    if (treatment.daily_cost < 0.0 || treatment.effectiveness < 0.0 || treatment.complication_risk < 0.0
        || treatment.complication_risk > 1.0) throw std::invalid_argument("invalid treatment values");
    character.treatments.push_back(std::move(treatment));
}

void LifeCoordinator::add_obligation(LifeObligation obligation) {
    if (obligation.amount_due < 0.0 || obligation.obligation_id.empty())
        throw std::invalid_argument("invalid obligation");
    for (const LifeObligation& existing : obligations_)
        if (existing.obligation_id == obligation.obligation_id)
            throw std::invalid_argument("duplicate obligation id");
    obligations_.push_back(std::move(obligation));
}

void LifeCoordinator::set_ghost_windows(std::vector<GhostTimeWindow> windows) {
    for (const GhostTimeWindow& window : windows)
        if (window.start_hour < 0.0 || window.end_hour > 24.0
            || window.start_hour >= window.end_hour || window.strength < 0.0)
            throw std::invalid_argument("invalid ghost time window");
    ghost_windows_ = std::move(windows);
}

bool LifeCoordinator::kill(const EntityId& id, std::uint64_t day, std::string cause) {
    LifeCharacter& character = find_character(id);
    if (character.status != LifeStatus::Active) return false;
    character.status = LifeStatus::Spectator;
    character.death_day = day;
    character.death_cause = std::move(cause);
    return true;
}

bool LifeCoordinator::enter_ghost(const EntityId& id) {
    LifeCharacter& character = find_character(id);
    if (character.status != LifeStatus::Spectator) return false;
    character.status = LifeStatus::Ghost;
    return true;
}

RecoveryRange LifeCoordinator::estimate_recovery(
    const EntityId& id, const std::string& condition_id) const {
    const LifeCharacter& character = find_character(id);
    const auto found = std::find_if(character.conditions.begin(), character.conditions.end(),
        [&condition_id](const MedicalCondition& condition) { return condition.condition_id == condition_id; });
    if (found == character.conditions.end()) throw std::out_of_range("medical condition not found");
    double factor = 1.0;
    double risk = 0.0;
    for (const MedicalTreatment& treatment : character.treatments) {
        if (!treatment.active || treatment.condition_id != condition_id) continue;
        factor += treatment.effectiveness;
        risk = 1.0 - (1.0 - risk) * (1.0 - clamp01(treatment.complication_risk));
    }
    const double expected = std::min(found->severity, found->recovery_per_day * factor);
    const double uncertainty = std::max(0.01, found->severity * 0.15);
    return {expected, std::max(0.0, expected - uncertainty),
            std::min(found->severity, expected + uncertainty), risk};
}

GhostInfluenceResult LifeCoordinator::attempt_ghost_influence(
    const EntityId& ghost_id, const EntityId& npc_id, const std::string& action,
    double hour_of_day, const WorldState& state, std::uint64_t random_sample) const {
    const auto ghost = characters_.find(ghost_id);
    const NPC* npc = find_npc(state, npc_id);
    if (ghost == characters_.end() || ghost->second.status != LifeStatus::Ghost)
        return {false, 0.0, "no active ghost"};
    if (npc == nullptr) return {false, 0.0, "NPC not found"};
    const auto window = std::find_if(ghost_windows_.begin(), ghost_windows_.end(),
        [hour_of_day](const GhostTimeWindow& value) {
            return hour_of_day >= value.start_hour && hour_of_day < value.end_hour;
        });
    if (window == ghost_windows_.end()) return {false, 0.0, "outside ghost time window"};
    const auto relationship = npc->relationships.find(ghost_id);
    const double trust = relationship == npc->relationships.end() ? 0.0 : relationship->second;
    double memory = 0.0;
    for (const NPCMemory& item : npc->memories) {
        if (item.target_entity_id == ghost_id)
            memory = std::max(memory, item.retention * (item.action_tag == ActionTag::InteractionPolite ? 0.5 : 1.0));
    }
    const auto trait = ghost->second.personality.find(npc_id);
    const double openness = trait == ghost->second.personality.end() ? 0.5 : clamp01(trait->second);
    const double score = clamp01(window->strength * (0.4 * openness + 0.3 * (trust + 1.0) / 2.0 + 0.3 * memory));
    const double sample = static_cast<double>(random_sample % 1000000U) / 1000000.0;
    (void)action; // Action type is supplied to the event layer; this method decides NPC receptivity.
    return {sample < score, score, sample < score ? "NPC accepted influence" :
        "NPC resisted based on personality, memory, and relationship"};
}

void LifeCoordinator::advance_day(WorldState& state, std::uint64_t day) {
    for (auto& [id, character] : characters_) {
        NPC* npc = find_npc(state, id);
        if (npc == nullptr || character.status != LifeStatus::Active) continue;
        double care_hours = 0.0;
        for (MedicalCondition& condition : character.conditions) {
            for (const MedicalTreatment& treatment : character.treatments) {
                if (!treatment.active || treatment.condition_id != condition.condition_id) continue;
                if (npc->money < treatment.daily_cost) continue;
                npc->money -= treatment.daily_cost;
                care_hours += std::max(0.0, treatment.daily_cost > 0.0 ? 1.0 : 0.0);
            }
            const RecoveryRange estimate = estimate_recovery(id, condition.condition_id);
            // A reproducible sample inside the uncertainty interval, keyed by day and condition.
            const std::uint64_t mix = day * 2654435761ULL
                + static_cast<std::uint64_t>(std::hash<std::string>{}(condition.condition_id));
            const double unit = static_cast<double>(mix % 10000ULL) / 10000.0;
            condition.severity = std::max(0.0, condition.severity
                - (estimate.lower + (estimate.upper - estimate.lower) * unit));
            care_hours += condition.severity * condition.care_hours_per_severity;
            if (condition.lasting_impairment && condition.severity <= 0.0)
                condition.severity = clamp01(condition.impairment_floor);
        }
        character.care_need_hours = std::max(0.0, care_hours);
        double capacity = 1.0;
        for (const MedicalCondition& condition : character.conditions) {
            const double limitation = condition.lasting_impairment && condition.severity <= 0.0
                ? condition.impairment_floor : condition.work_capacity_at_full_severity;
            capacity = std::min(capacity, 1.0 - condition.severity * (1.0 - limitation));
        }
        // The existing world coordinator settles wages and missed-work penalties.
        // Reduce recorded attendance here so its established economic path applies them once.
        npc->work_hours_today = std::clamp(npc->work_hours_today * capacity, 0.0, 8.0);
    }

    for (LifeObligation& obligation : obligations_) {
        if (obligation.settled || obligation.missed) continue;
        const auto debtor = characters_.find(obligation.debtor_id);
        NPC* debtor_npc = find_npc(state, obligation.debtor_id);
        NPC* creditor_npc = find_npc(state, obligation.creditor_id);
        if (debtor != characters_.end() && debtor->second.status != LifeStatus::Active && debtor_npc != nullptr) {
            const double paid = std::min(std::max(0.0, debtor_npc->money), obligation.amount_due);
            if (creditor_npc != nullptr) creditor_npc->money += paid;
            debtor_npc->money -= paid;
            obligation.amount_due -= paid;
            if (obligation.amount_due <= 1e-9) obligation.settled = true;
            else {
                NPC* helper = nullptr;
                double best = 0.55;
                for (NPC& candidate : state.npcs) {
                    if (candidate.entity_id == obligation.debtor_id || candidate.entity_id == obligation.creditor_id) continue;
                    const auto tie = candidate.relationships.find(obligation.debtor_id);
                    const double score = tie == candidate.relationships.end() ? 0.0
                        : tie->second * 0.5 + candidate.moral_shackle * 0.25
                            + (1.0 - candidate.desperation_index) * 0.25;
                    if (score > best) { best = score; helper = &candidate; }
                }
                if (helper != nullptr && helper->money >= obligation.amount_due) {
                    helper->money -= obligation.amount_due;
                    if (creditor_npc != nullptr) creditor_npc->money += obligation.amount_due;
                    obligation.amount_due = 0.0;
                    obligation.settled = true;
                }
            }
        } else if (day > obligation.due_day) {
            obligation.missed = true;
            if (debtor_npc != nullptr) debtor_npc->personal_stress = clamp01(debtor_npc->personal_stress + 0.1);
            if (debtor_npc != nullptr) {
                const auto tie = debtor_npc->relationships.find(obligation.creditor_id);
                if (tie != debtor_npc->relationships.end()) tie->second = std::max(-1.0, tie->second - 0.15);
            }
        }
    }
}

} // namespace simreality
