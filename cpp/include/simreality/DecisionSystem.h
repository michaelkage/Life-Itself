#pragma once

#include "simreality/CoreTypes.h"

#include <string>

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

// Deterministic utility-based choice for unscheduled NPC hours. Explicit schedule
// entries always take precedence; this function supplies an explainable fallback.
[[nodiscard]] ActivityDecision choose_activity(
    const NPC& npc, const District* district, const ActivityContext& context);

} // namespace simreality
