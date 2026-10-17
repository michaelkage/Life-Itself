#include "simreality/Justice.h"

#include <algorithm>
#include <cmath>
#include <map>
#include <sstream>

namespace simreality {
namespace {
double round_ties_to_even(double value) noexcept {
    const double lower = std::floor(value);
    const double fraction = value - lower;
    if (fraction < 0.5) return lower;
    if (fraction > 0.5) return lower + 1.0;
    return std::fmod(std::abs(lower), 2.0) == 0.0 ? lower : lower + 1.0;
}

double severity_for(ActionTag action_tag) noexcept {
    switch (action_tag) {
    case ActionTag::InteractionPolite: return 0.0;
    case ActionTag::CrimeVandalism: return 0.20;
    case ActionTag::CrimeTheft: return 0.35;
    case ActionTag::CrimeAssault: return 0.70;
    case ActionTag::CrimeArmedAssault: return 1.00;
    }
    return 0.0;
}

const char* action_name(ActionTag action_tag) noexcept {
    switch (action_tag) {
    case ActionTag::InteractionPolite: return "Interaction.Polite";
    case ActionTag::CrimeTheft: return "Crime.Theft";
    case ActionTag::CrimeAssault: return "Crime.Assault";
    case ActionTag::CrimeArmedAssault: return "Crime.ArmedAssault";
    case ActionTag::CrimeVandalism: return "Crime.Vandalism";
    }
    return "Unknown";
}

double stacking_strength(EvidenceKind evidence) noexcept {
    switch (evidence) {
    case EvidenceKind::Unwitnessed: return 0.30;
    case EvidenceKind::SingleWitness: return 0.70;
    case EvidenceKind::Corroborated:
    case EvidenceKind::Confessed: return 1.00;
    }
    return 0.0;
}

}

double Charge::severity() const noexcept {
    return severity_for(action_tag);
}

bool Charge::provable() const noexcept {
    return evidence != EvidenceKind::Unwitnessed;
}

double Charge::sentence() const noexcept {
    return round_ties_to_even(30.0 * severity() * strength);
}

double Conviction::severity() const noexcept {
    return severity_for(action_tag);
}

double CriminalFile::severity_total() const noexcept {
    double total = 0.0;
    for (const Charge& charge : charges) {
        if (charge.provable()) total += charge.severity() * charge.strength;
    }
    return total;
}

double CriminalFile::sentence_if_convicted() const noexcept {
    double total = 0.0;
    for (const Charge& charge : charges) {
        if (charge.provable()) total += charge.sentence();
    }
    return total;
}

std::vector<Charge> CriminalFile::provable_charges() const {
    std::vector<Charge> result;
    for (const Charge& charge : charges) {
        if (charge.provable()) result.push_back(charge);
    }
    return result;
}

bool CriminalFile::is_prosecutable() const noexcept {
    return std::any_of(charges.begin(), charges.end(),
        [](const Charge& charge) { return charge.provable(); });
}

const Conviction* CriminalFile::most_recent_conviction() const noexcept {
    if (convictions.empty()) return nullptr;
    return &*std::max_element(convictions.begin(), convictions.end(),
        [](const Conviction& a, const Conviction& b) {
            return a.convicted_on_day < b.convicted_on_day;
        });
}

Charge charge_from_memory(const NPCMemory& memory) {
    if (memory.is_actionable()) {
        return {memory.action_tag, EvidenceKind::SingleWitness,
            stacking_strength(EvidenceKind::SingleWitness)};
    }
    return {memory.action_tag, EvidenceKind::Unwitnessed,
        stacking_strength(EvidenceKind::Unwitnessed)};
}

CriminalFile file_from_memories(
    const EntityId& player_id, const std::vector<NPCMemory>& memories) {
    std::map<ActionTag, std::vector<NPCMemory>> by_action;
    for (const NPCMemory& memory : memories) {
        if (memory.target_entity_id == player_id) {
            by_action[memory.action_tag].push_back(memory);
        }
    }

    CriminalFile result;
    result.player_id = player_id;
    for (const auto& [action, witnesses] : by_action) {
        const auto best = std::max_element(witnesses.begin(), witnesses.end(),
            [](const NPCMemory& a, const NPCMemory& b) { return a.retention < b.retention; });
        Charge charge = charge_from_memory(*best);
        if (witnesses.size() >= 2 && charge.provable()) {
            charge = {action, EvidenceKind::Corroborated,
                stacking_strength(EvidenceKind::Corroborated)};
        }
        result.charges.push_back(charge);
    }
    return result;
}

Conviction convict(
    CriminalFile& criminal_file, ActionTag action_tag,
    std::uint32_t current_day, double sentence_days) {
    const Conviction result{action_tag, current_day, sentence_days};
    criminal_file.convictions.push_back(result);
    return result;
}

void register_bribe_attempt(CriminalFile& criminal_file) {
    ++criminal_file.bribe_attempts;
    criminal_file.charges.push_back(
        {ActionTag::CrimeTheft, EvidenceKind::Confessed,
            stacking_strength(EvidenceKind::SingleWitness)});
}

double enforcement_probability(ActionTag action_tag, double corruption) noexcept {
    const double severity = severity_for(action_tag);
    if (severity <= 0.0) return 1.0;
    if (severity >= kMinorOffenceCutoff) {
        return std::max(1.0 - 0.1 * corruption, kEnforcementFloor);
    }
    return std::max(1.0 - corruption, kEnforcementFloor);
}

Consequence consequence_for(
    ActionTag action_tag, const CriminalFile& criminal_file, const District& district,
    const EntityId& officer_entity_id, double corruption, double rng) {
    if (rng >= enforcement_probability(action_tag, corruption)) {
        return std::monostate{};
    }

    const auto found = std::find_if(criminal_file.charges.begin(), criminal_file.charges.end(),
        [action_tag](const Charge& charge) {
            return charge.action_tag == action_tag && charge.provable();
        });
    if (found == criminal_file.charges.end()) {
        return Stop{std::string(action_name(action_tag)) +
            " reported, but no provable charge on the file", true};
    }
    return Arrest{&criminal_file, *found, officer_entity_id, district.district_id};
}

std::optional<PleaOffer> plea_offer(const CriminalFile& criminal_file) {
    const std::vector<Charge> provable = criminal_file.provable_charges();
    if (provable.empty()) return std::nullopt;

    const auto principal = std::max_element(provable.begin(), provable.end(),
        [](const Charge& a, const Charge& b) {
            return a.severity() * a.strength < b.severity() * b.strength;
        });
    std::vector<Charge> dropped;
    for (const Charge& charge : provable) {
        if (&charge != &*principal) dropped.push_back(charge);
    }

    const double trial_total = criminal_file.sentence_if_convicted();
    const double concession = 0.55 + 0.15 * std::min(1.0, static_cast<double>(dropped.size()));
    const double accepted = principal->sentence() * concession;
    const double saving = std::max(0.0, trial_total - principal->sentence() - accepted);

    std::ostringstream note;
    note << "Concede " << action_name(principal->action_tag) << ", drop "
         << dropped.size() << " other charge(s), " << round_ties_to_even(saving)
         << " days saved.";
    return PleaOffer{*principal, std::move(dropped), round_ties_to_even(accepted),
        round_ties_to_even(trial_total), note.str()};
}

} // namespace simreality
