#include "simreality/Reputation.h"

#include <algorithm>
#include <cmath>
#include <map>

namespace simreality {
namespace {
double severity_for(ActionTag action_tag) noexcept {
    switch (action_tag) {
    case ActionTag::InteractionPolite:
    case ActionTag::GhostSign:
    case ActionTag::GhostSound:
    case ActionTag::GhostDream: return 0.0;
    case ActionTag::CrimeVandalism: return 0.20;
    case ActionTag::CrimeTheft: return 0.35;
    case ActionTag::CrimeAssault: return 0.70;
    case ActionTag::CrimeArmedAssault: return 1.00;
    }
    return 0.0;
}
}

const char* ReputationProfile::source() const noexcept {
    return record_penalty >= accusation_penalty ? "record" : "accusation";
}

bool ReputationProfile::clean() const noexcept {
    return accusation_penalty <= 0.0 && record_penalty <= 0.0;
}

double accusation_penalty(
    const std::vector<NPCMemory>& memories, const EntityId& player_id) {
    std::map<ActionTag, double> strongest;
    for (const NPCMemory& memory : memories) {
        if (memory.target_entity_id != player_id || !memory.is_actionable()) continue;
        const double weight = severity_for(memory.action_tag) *
            memory.retention * kAccusationGain;
        strongest[memory.action_tag] = std::max(strongest[memory.action_tag], weight);
    }
    double remaining = 1.0;
    for (const auto& [action, weight] : strongest) {
        (void)action;
        remaining *= 1.0 - weight;
    }
    return 1.0 - remaining;
}

double record_penalty(const CriminalFile* criminal_file, std::uint32_t current_day) {
    if (criminal_file == nullptr) return 0.0;
    const Conviction* conviction = criminal_file->most_recent_conviction();
    if (conviction == nullptr) return 0.0;

    const std::uint32_t days_served = current_day >= conviction->convicted_on_day
        ? current_day - conviction->convicted_on_day : 0;
    const double past_sentence = std::max(
        0.0, static_cast<double>(days_served) - conviction->sentence_days);
    const double salience = kRecordFloor +
        (1.0 - kRecordFloor) * std::pow(kRecordDecayPerDay, past_sentence);
    return conviction->severity() * salience;
}

ReputationProfile local_reputation(
    const std::vector<NPCMemory>& memories, const EntityId& player_id,
    const CriminalFile* criminal_file, std::uint32_t current_day) {
    const double accusation = accusation_penalty(memories, player_id);
    const double record = record_penalty(criminal_file, current_day);
    const double penalty = std::max(accusation, record);
    return {std::clamp(1.0 - penalty, 0.0, 1.0), accusation, record};
}

} // namespace simreality
