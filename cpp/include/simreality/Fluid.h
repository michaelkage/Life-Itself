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

enum class BackendKind : std::uint8_t { Cpu, Gpu };

struct ComputeBackendInfo {
    std::string name{};
    bool available{false};
    std::size_t maximum_agents{0};
};

class ComputeBackend {
public:
    virtual ~ComputeBackend() = default;
    [[nodiscard]] virtual ComputeBackendInfo info() const = 0;
    [[nodiscard]] virtual std::vector<AgentOutput> evaluate(
        const std::vector<AgentInput>& agents) = 0;
};

struct EvaluationOptions {
    std::size_t minimum_gpu_batch{2048};
    // GPU pressure may differ slightly from the f32 CPU reference across devices.
    float maximum_score_error{1.0e-5F};
};

struct EvaluationReport {
    std::vector<AgentOutput> agents{};
    BackendKind backend{BackendKind::Cpu};
    std::string backend_name{"CPU reference"};
    bool gpu_fallback{false};
};

void validate_agents(const std::vector<AgentInput>& agents);
[[nodiscard]] EvaluationReport evaluate_with_fallback(
    const std::vector<AgentInput>& agents, ComputeBackend* backend = nullptr,
    EvaluationOptions options = {});

[[nodiscard]] std::vector<std::uint8_t> pack_agents(const std::vector<AgentInput>& agents);
[[nodiscard]] std::vector<AgentOutput> evaluate_cpu(const std::vector<AgentInput>& agents);
[[nodiscard]] std::vector<AgentOutput> unpack_outputs(
    const std::vector<AgentInput>& agents, const std::vector<std::uint8_t>& bytes);

} // namespace simreality::fluid
