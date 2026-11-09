#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace simreality::fluid {

inline constexpr std::size_t kAgentInputStride = 48;
inline constexpr std::size_t kAgentOutputStride = 16;
inline constexpr float kRumourAttributionThreshold = 0.6F;
inline constexpr float kRumourFloorAttributed = 0.05F;
inline constexpr float kRumourFloorUnattributed = 0.01F;

// Immutable numerical snapshot. All channels except world coordinates are normalized.
struct AgentInput {
    std::string agent_id{};
    float x{0.0F};
    float y{0.0F};
    float moral_shackle{0.0F};
    float personal_stress{0.0F};
    float overpopulation{0.0F};
    float supply_shortage{0.0F};
    float weather_severity{0.0F};
    float local_corruption{0.0F};
    float rumour_retention{0.0F};
    float speaker_fidelity{0.5F};
    float description_uncertainty{0.0F};
    bool target_known{false};
};

struct AgentOutput {
    std::string agent_id{};
    float desperation_index{0.0F};
    std::uint8_t trauma_tier{0};
    bool rumour_transmittable{false};
    bool attribution_survives{false};
};

// Explicit little-endian f32 layout matching shaders/sre_fluid_agent.wgsl.
[[nodiscard]] std::vector<std::uint8_t> pack_agents(const std::vector<AgentInput>& agents);
[[nodiscard]] std::vector<AgentOutput> evaluate_cpu(const std::vector<AgentInput>& agents);

} // namespace simreality::fluid
