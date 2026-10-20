#pragma once

#include "simreality/CoreTypes.h"

#include <cstddef>
#include <string>
#include <vector>

namespace simreality {

struct WorldMetrics {
    std::size_t residents{0};
    std::size_t housed_residents{0};
    std::size_t employed_residents{0};
    std::size_t open_businesses{0};
    std::size_t unresolved_events{0};
    double resident_cash{0.0};
    double business_cash{0.0};
    double available_business_stock{0.0};
    double average_stress{0.0};
    double average_isolation{0.0};
    double average_social_need{0.0};
};

struct WorldInvariantReport {
    std::vector<std::string> violations{};
    [[nodiscard]] bool valid() const noexcept { return violations.empty(); }
};

// Read-only observability for tests, debugging tools and a future Unreal adapter.
[[nodiscard]] WorldMetrics collect_world_metrics(const WorldState& state);
[[nodiscard]] WorldInvariantReport validate_world_state(const WorldState& state);

} // namespace simreality
