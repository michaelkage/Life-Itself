#include "simreality/DecisionSystem.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace simreality {

MoralChoiceExplanation explain_moral_choice(
    const NPC& npc, const MoralChoiceOption& option) {
    const auto unit = [](double value) { return std::clamp(value, 0.0, 1.0); };
    const double compassion = unit(npc.compassion);
    const double fairness = unit(npc.fairness_value);
    const double safety = unit(npc.safety_value);
    const double freedom = unit(npc.freedom_value);
    const double loyalty = unit(npc.loyalty_bias);
    const double self_interest = unit(npc.self_interest_value);

    MoralChoiceExplanation explanation;
    explanation.option_id = option.option_id;
    explanation.factors = {
        {"urgency", compassion, unit(option.urgency),
            0.25 * compassion * unit(option.urgency)},
        {"people_helped", compassion, unit(option.people_helped),
            0.20 * compassion * unit(option.people_helped)},
        {"fairness", fairness, unit(option.fairness),
            0.20 * fairness * unit(option.fairness)},
        {"safety", safety, unit(option.safety),
            0.15 * safety * unit(option.safety)},
        {"freedom", freedom, unit(option.freedom),
            0.10 * freedom * unit(option.freedom)},
        {"loyalty", loyalty, unit(option.loyalty),
            0.10 * loyalty * unit(option.loyalty)},
        {"personal_cost", self_interest, unit(option.personal_cost),
            0.20 * self_interest * (1.0 - unit(option.personal_cost))}
    };
    for (const MoralChoiceFactorExplanation& factor : explanation.factors) {
        explanation.total_score += factor.contribution;
    }
    return explanation;
}

MoralChoiceEvaluation evaluate_moral_choice(
    const NPC& npc, const MoralChoiceOption& option) {
    const MoralChoiceExplanation explanation = explain_moral_choice(npc, option);
    return {explanation.option_id, explanation.total_score};
}

MoralChoiceEvaluation choose_moral_option(
    const NPC& npc, const std::vector<MoralChoiceOption>& options) {
    if (options.empty()) {
        throw std::invalid_argument("moral choice requires at least one option");
    }
    MoralChoiceEvaluation best = evaluate_moral_choice(npc, options.front());
    for (std::size_t i = 1; i < options.size(); ++i) {
        const MoralChoiceEvaluation candidate = evaluate_moral_choice(npc, options[i]);
        if (candidate.score > best.score) {
            best = candidate;
        }
    }
    return best;
}

MoralChoiceResolution resolve_moral_choice(
    NPC& npc, const std::vector<MoralChoiceOption>& options,
    const std::vector<MoralChoiceConsequence>& consequences) {
    const auto finite = [](double value) { return std::isfinite(value); };
    std::vector<std::string> option_ids;
    option_ids.reserve(options.size());
    for (const MoralChoiceOption& option : options) {
        if (option.option_id.empty()
            || std::find(option_ids.begin(), option_ids.end(), option.option_id) != option_ids.end()) {
            throw std::invalid_argument("moral choice option IDs must be non-empty and unique");
        }
        option_ids.push_back(option.option_id);
    }

    const MoralChoiceConsequence* selected_consequence = nullptr;
    std::vector<std::string> consequence_ids;
    consequence_ids.reserve(consequences.size());
    for (const MoralChoiceConsequence& consequence : consequences) {
        if (consequence.option_id.empty()
            || std::find(consequence_ids.begin(), consequence_ids.end(), consequence.option_id)
                != consequence_ids.end()) {
            throw std::invalid_argument("moral consequence IDs must be non-empty and unique");
        }
        consequence_ids.push_back(consequence.option_id);
        if (!finite(consequence.money_delta) || !finite(consequence.stress_delta)) {
            throw std::invalid_argument("moral consequences must be finite");
        }
        for (const auto& [entity_id, delta] : consequence.relationship_deltas) {
            if (entity_id.empty() || !finite(delta)) {
                throw std::invalid_argument("relationship consequences require an entity and finite delta");
            }
        }
        if (std::find(option_ids.begin(), option_ids.end(), consequence.option_id) == option_ids.end()) {
            throw std::invalid_argument("moral consequence references an unknown option");
        }
    }

    const MoralChoiceEvaluation choice = choose_moral_option(npc, options);
    for (const MoralChoiceConsequence& consequence : consequences) {
        if (consequence.option_id == choice.option_id) {
            selected_consequence = &consequence;
            break;
        }
    }

    MoralChoiceResolution resolution;
    resolution.choice = choice;
    if (selected_consequence == nullptr) return resolution;

    const double next_money = std::max(0.0, npc.money + selected_consequence->money_delta);
    const double next_stress = std::clamp(
        npc.personal_stress + selected_consequence->stress_delta, 0.0, 1.0);
    resolution.money_delta_applied = next_money - npc.money;
    resolution.stress_delta_applied = next_stress - npc.personal_stress;

    std::map<EntityId, double> next_relationships;
    for (const auto& [entity_id, delta] : selected_consequence->relationship_deltas) {
        const auto current = npc.relationships.find(entity_id);
        const double previous = current == npc.relationships.end() ? 0.0 : current->second;
        const double next = std::clamp(previous + delta, -1.0, 1.0);
        next_relationships.emplace(entity_id, next);
        resolution.relationship_deltas_applied.emplace(entity_id, next - previous);
    }

    npc.money = next_money;
    npc.personal_stress = next_stress;
    for (const auto& [entity_id, value] : next_relationships) {
        npc.relationships[entity_id] = value;
    }
    return resolution;
}

ActivityDecision choose_activity(
    const NPC& npc, const District* district, const ActivityContext& context) {
    const double stress = std::clamp(npc.personal_stress, 0.0, 1.0);
    const double social_need = std::clamp(npc.social_need, 0.0, 1.0);
    const double isolation = std::clamp(npc.isolation, 0.0, 1.0);
    const bool night = context.hour >= 22U || context.hour < 6U;
    const bool commute_window = context.hour >= 7U && context.hour < 9U;
    const bool work_window = context.hour >= 9U && context.hour < 17U;
    const bool has_job = !npc.job_id.empty();
    const bool has_home = !npc.home_id.empty();
    const double service_capacity = district == nullptr ? 0.0
        : std::clamp(district->service_capacity, 0.0, 1.0);
    const double transport = district == nullptr ? 1.0
        : std::clamp(district->transport_reliability, 0.0, 1.0);

    struct Candidate { DailyActivity activity; double score; const char* reason; };
    const std::array<Candidate, 8> candidates{{
        {DailyActivity::Sleep, night ? 100.0 : 0.0, "night-time recovery"},
        {DailyActivity::Commute, has_job && commute_window ? 75.0 + transport * 15.0 : 0.0,
            "travel to scheduled employment"},
        {DailyActivity::Work, has_job && work_window ? 75.0 : 0.0,
            "attend employment during working hours"},
        {DailyActivity::Shop, context.has_open_shop && npc.money > 0.0
            ? 4.0 + std::min(npc.money, 100.0) * 0.04 : 0.0,
            "obtain goods from an available local business"},
        {DailyActivity::Socialise, night ? 0.0
            : 8.0 + social_need * 36.0 + isolation * 14.0
                + (context.trusted_contact_available ? 8.0 : 0.0),
            "reduce unmet social needs and maintain relationships"},
        {DailyActivity::Service, !night && context.service_available
            ? 4.0 + stress * 28.0 + (1.0 - service_capacity) * 4.0 : 0.0,
            "seek support or recover through local services"},
        {DailyActivity::Leisure, night ? 0.0 : 7.0 + stress * 8.0,
            "take discretionary time to recover"},
        {DailyActivity::Home, night ? 0.0
            : (has_home ? 6.0 : 1.0) + (npc.trauma_level >= TraumaLevel::Paranoid ? 24.0 : 0.0)
                + (stress > 0.8 ? 5.0 : 0.0),
            "remain in a familiar or lower-stimulation place"}
    }};

    // Stable candidate order provides deterministic tie-breaking.
    const Candidate* best = &candidates.front();
    double best_score = -1.0;
    for (const Candidate& candidate : candidates) {
        double score = candidate.score;
        if (candidate.activity == DailyActivity::Commute && transport < 0.3) score *= 0.25;
        if (candidate.activity == DailyActivity::Home && !has_home) score *= 0.5;
        if (score > best_score) {
            best = &candidate;
            best_score = score;
        }
    }
    return {best->activity, best_score, best->reason};
}

} // namespace simreality
