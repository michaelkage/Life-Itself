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

// Deterministic utility-based choice for unscheduled NPC hours. Explicit schedule
// entries always take precedence; this function supplies an explainable fallback.
[[nodiscard]] ActivityDecision choose_activity(
    const NPC& npc, const District* district, const ActivityContext& context);

} // namespace simreality
