#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>
#include <span>
#include <string>
#include <vector>

namespace simreality::fluid {

inline constexpr std::size_t kAgentInputStride = 48;
inline constexpr std::size_t kAgentOutputStride = 16;
inline constexpr std::size_t kWorkgroupSize = 256;

struct DispatchLimits {
    // Maximum number of agents addressable by one dispatch's storage buffers.
    std::size_t maximum_agents{0U};
    // Device limit for workgroups dispatched along the x dimension.
    std::size_t maximum_workgroups_per_dimension{0U};
    std::size_t workgroup_size{kWorkgroupSize};
    // Maximum byte sizes of the input and output storage-buffer bindings.
    std::size_t maximum_input_buffer_bytes{std::numeric_limits<std::size_t>::max()};
    std::size_t maximum_output_buffer_bytes{std::numeric_limits<std::size_t>::max()};
};

struct DispatchRange {
    std::size_t agent_offset{0U};
    std::size_t agent_count{0U};
    std::size_t workgroup_count{0U};
};

// Build bounded, contiguous dispatches. All non-final chunks are workgroup
// aligned; the final chunk may be partial and is protected by shader bounds checks.
[[nodiscard]] std::vector<DispatchRange> plan_dispatches(
    std::size_t agent_count, DispatchLimits limits);
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
    std::size_t maximum_workgroups_per_dimension{65535U};
    std::size_t workgroup_size{kWorkgroupSize};
    std::size_t maximum_input_buffer_bytes{std::numeric_limits<std::size_t>::max()};
    std::size_t maximum_output_buffer_bytes{std::numeric_limits<std::size_t>::max()};
};

class ComputeBackend {
public:
    virtual ~ComputeBackend() = default;
    [[nodiscard]] virtual ComputeBackendInfo info() const = 0;
    [[nodiscard]] virtual std::vector<AgentOutput> evaluate(
        std::span<const AgentInput> agents) = 0;
};

struct BufferViews {
    std::span<std::uint8_t> input{};
    std::span<std::uint8_t> output{};
};

// Retains CPU staging/readback allocations between ticks. prepare() exposes
// only the active byte ranges while keeping the full allocation size unchanged.
// Returned spans are valid until a later prepare() grows the workspace; callers
// must finish using them before the next prepare() call. This class is not
// thread-safe and does not clear retained bytes between ticks.
class BufferWorkspace {
public:
    [[nodiscard]] BufferViews prepare(std::size_t agent_count);
    [[nodiscard]] std::size_t capacity_agents() const noexcept {
        return capacity_agents_;
    }

private:
    std::vector<std::uint8_t> input_{};
    std::vector<std::uint8_t> output_{};
    std::size_t capacity_agents_{0U};
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

// Fill caller-owned staging memory. Adapters can retain these allocations across
// ticks instead of allocating a fresh byte vector for every GPU upload.
void pack_agents_into(std::span<const AgentInput> agents,
    std::span<std::uint8_t> destination);
[[nodiscard]] EvaluationReport evaluate_with_fallback(
    const std::vector<AgentInput>& agents, ComputeBackend* backend = nullptr,
    EvaluationOptions options = {});

[[nodiscard]] std::vector<std::uint8_t> pack_agents(const std::vector<AgentInput>& agents);
[[nodiscard]] std::vector<AgentOutput> evaluate_cpu(std::span<const AgentInput> agents);
[[nodiscard]] std::vector<AgentOutput> unpack_outputs(
    std::span<const AgentInput> agents, std::span<const std::uint8_t> bytes);

} // namespace simreality::fluid
