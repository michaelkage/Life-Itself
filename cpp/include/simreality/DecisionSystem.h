#pragma once

#include "simreality/CoreTypes.h"

#include <string>
#include <vector>

namespace simreality {

struct ActivityContext {
    std::uint8_t hour{12};
    bool has_open_shop{false};
    bool service_available{false};
    bool trusted_contact_available{false};
};

struct ActivityDecision {
    DailyActivity activity{DailyActivity::Leisure};
    double score{0.0};
    std::string reason{};
};

// Each option dimension is normalized to [0, 1]. These are scenario features,
// not moral labels: higher values mean more of the named property.
struct MoralChoiceOption {
    std::string option_id{};
    double urgency{0.0};
    double people_helped{0.0};
    double fairness{0.0};
    double safety{0.0};
    double freedom{0.0};
    double loyalty{0.0};
    double personal_cost{0.0};
};

struct MoralChoiceEvaluation {
    std::string option_id{};
    double score{0.0};
};

// Deterministic value-weighted evaluation. It scores options but does not
// dictate a universal good/bad answer or mutate the NPC/world.
[[nodiscard]] MoralChoiceEvaluation evaluate_moral_choice(
    const NPC& npc, const MoralChoiceOption& option);

// Returns the highest-scoring option. Equal scores preserve input order, so
// callers can make replay-stable choices without a random tie-breaker.
// An empty option list is a caller error and throws std::invalid_argument.
[[nodiscard]] MoralChoiceEvaluation choose_moral_option(
    const NPC& npc, const std::vector<MoralChoiceOption>& options);

// Consequences are scenario-authored, not inferred from a score. Only the
// selected option's entry is applied. Relationship changes are directed from
// the deciding NPC toward each named entity.
struct MoralChoiceConsequence {
    std::string option_id{};
    double money_delta{0.0};
    double stress_delta{0.0};
    std::map<EntityId, double> relationship_deltas{};
};

struct MoralChoiceResolution {
    MoralChoiceEvaluation choice{};
    double money_delta_applied{0.0};
    double stress_delta_applied{0.0};
    std::map<EntityId, double> relationship_deltas_applied{};
};

// Selects an option and applies its explicitly authored effects to the NPC.
// Money is floored at zero; stress and relationships are clamped to [0, 1]
// and [-1, 1] respectively. Invalid/ambiguous scenario data throws without
// partially applying effects.
[[nodiscard]] MoralChoiceResolution resolve_moral_choice(
    NPC& npc, const std::vector<MoralChoiceOption>& options,
    const std::vector<MoralChoiceConsequence>& consequences);

// Deterministic utility-based choice for unscheduled NPC hours. Explicit schedule
// entries always take precedence; this function supplies an explainable fallback.
[[nodiscard]] ActivityDecision choose_activity(
    const NPC& npc, const District* district, const ActivityContext& context);

} // namespace simreality
