#include "simreality/Fluid.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>
#include <unordered_set>

namespace simreality::fluid {
namespace {

void require_finite(float value, const char* name) {
    if (!std::isfinite(value)) {
        throw std::invalid_argument(std::string(name) + " must be finite");
    }
}

void require_unit(float value, const char* name) {
    require_finite(value, name);
    if (value < 0.0F || value > 1.0F) {
        throw std::invalid_argument(std::string(name) + " must be in [0, 1]");
    }
}

void validate_impl(std::span<const AgentInput> agents) {
    std::unordered_set<std::string> ids;
    ids.reserve(agents.size());
    for (const AgentInput& agent : agents) {
        if (agent.agent_id.empty()) {
            throw std::invalid_argument("agent_id must not be empty");
        }
        if (!ids.insert(agent.agent_id).second) {
            throw std::invalid_argument("agent IDs must be unique within a batch");
        }
        require_finite(agent.x, "x");
        require_finite(agent.y, "y");
        require_unit(agent.moral_shackle, "moral_shackle");
        require_unit(agent.personal_stress, "personal_stress");
        require_unit(agent.overpopulation, "overpopulation");
        require_unit(agent.supply_shortage, "supply_shortage");
        require_unit(agent.weather_severity, "weather_severity");
        require_unit(agent.local_corruption, "local_corruption");
        require_unit(agent.rumour_retention, "rumour_retention");
        require_unit(agent.speaker_fidelity, "speaker_fidelity");
        require_unit(agent.description_uncertainty, "description_uncertainty");
    }
}

float read_f32_le(const std::uint8_t* bytes) {
    const std::uint32_t bits = static_cast<std::uint32_t>(bytes[0])
        | (static_cast<std::uint32_t>(bytes[1]) << 8U)
        | (static_cast<std::uint32_t>(bytes[2]) << 16U)
        | (static_cast<std::uint32_t>(bytes[3]) << 24U);
    return std::bit_cast<float>(bits);
}

void append_f32_le(std::vector<std::uint8_t>& bytes, float value) {
    const std::uint32_t bits = std::bit_cast<std::uint32_t>(value);
    bytes.push_back(static_cast<std::uint8_t>(bits & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 8U) & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 16U) & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 24U) & 0xffU));
}

} // namespace

void pack_agents_into(std::span<const AgentInput> agents,
    std::span<std::uint8_t> destination) {
    validate_impl(agents);
    if (agents.size() > std::numeric_limits<std::size_t>::max() / kAgentInputStride
        || destination.size() != agents.size() * kAgentInputStride) {
        throw std::invalid_argument("agent staging buffer has an invalid byte length");
    }
    std::size_t offset = 0U;
    const auto write = [&destination, &offset](float value) {
        const std::uint32_t bits = std::bit_cast<std::uint32_t>(value);
        destination[offset++] = static_cast<std::uint8_t>(bits & 0xffU);
        destination[offset++] = static_cast<std::uint8_t>((bits >> 8U) & 0xffU);
        destination[offset++] = static_cast<std::uint8_t>((bits >> 16U) & 0xffU);
        destination[offset++] = static_cast<std::uint8_t>((bits >> 24U) & 0xffU);
    };
    for (const AgentInput& a : agents) {
        write(a.x); write(a.y); write(a.moral_shackle); write(a.personal_stress);
        write(a.overpopulation); write(a.supply_shortage); write(a.weather_severity);
        write(a.local_corruption); write(a.rumour_retention); write(a.speaker_fidelity);
        write(a.description_uncertainty); write(a.target_known ? 1.0F : 0.0F);
    }
}

std::vector<std::uint8_t> pack_agents(const std::vector<AgentInput>& agents) {
    if (agents.size() > std::numeric_limits<std::size_t>::max() / kAgentInputStride) {
        throw std::length_error("agent batch is too large to pack");
    }
    std::vector<std::uint8_t> bytes(agents.size() * kAgentInputStride);
    pack_agents_into(agents, bytes);
    return bytes;
}

std::vector<AgentOutput> evaluate_cpu(std::span<const AgentInput> agents) {
    validate_impl(agents);
    std::vector<AgentOutput> outputs;
    outputs.reserve(agents.size());
    for (const AgentInput& a : agents) {
        const float pressure = std::clamp(
            (a.overpopulation * 1.2F + a.supply_shortage * 1.5F
                + a.weather_severity * 0.8F + a.local_corruption * 1.1F) / 4.6F,
            0.0F, 1.0F);
        const std::uint8_t personal = a.personal_stress >= 0.45F ? 2U
            : (a.personal_stress >= 0.10F ? 1U : 0U);
        const std::uint8_t environmental = pressure >= 0.90F ? 3U
            : (pressure >= 0.75F ? 2U : (pressure >= 0.60F ? 1U : 0U));
        const bool attributed_input = a.target_known
            && a.rumour_retention >= kRumourAttributionThreshold;
        const float floor = attributed_input
            ? kRumourFloorAttributed : kRumourFloorUnattributed;
        const bool transmittable = a.rumour_retention > floor;
        outputs.push_back({a.agent_id, pressure, std::max(personal, environmental),
            transmittable, transmittable && attributed_input});
    }
    return outputs;
}


void validate_agents(const std::vector<AgentInput>& agents) {
    validate_impl(agents);
}


std::vector<AgentOutput> unpack_outputs(
    std::span<const AgentInput> agents, std::span<const std::uint8_t> bytes) {
    validate_impl(agents);
    if (agents.size() > std::numeric_limits<std::size_t>::max() / kAgentOutputStride
        || bytes.size() != agents.size() * kAgentOutputStride) {
        throw std::invalid_argument("GPU output buffer has an invalid byte length");
    }
    std::vector<AgentOutput> outputs;
    outputs.reserve(agents.size());
    for (std::size_t i = 0; i < agents.size(); ++i) {
        const std::uint8_t* record = bytes.data() + i * kAgentOutputStride;
        const float desperation = read_f32_le(record);
        const float trauma = read_f32_le(record + 4);
        const float transmittable = read_f32_le(record + 8);
        const float attribution = read_f32_le(record + 12);
        if (!std::isfinite(desperation) || desperation < 0.0F || desperation > 1.0F
            || !std::isfinite(trauma) || trauma < 0.0F || trauma > 3.0F
            || std::floor(trauma) != trauma
            || (transmittable != 0.0F && transmittable != 1.0F)
            || (attribution != 0.0F && attribution != 1.0F)
            || (attribution == 1.0F && transmittable != 1.0F)) {
            throw std::invalid_argument("GPU output buffer contains an invalid agent result");
        }
        outputs.push_back({agents[i].agent_id, desperation,
            static_cast<std::uint8_t>(trauma), transmittable == 1.0F,
            attribution == 1.0F});
    }
    return outputs;
}

EvaluationReport evaluate_with_fallback(
    const std::vector<AgentInput>& agents, ComputeBackend* backend,
    EvaluationOptions options) {
    validate_agents(agents);
    if (!std::isfinite(options.maximum_score_error) || options.maximum_score_error < 0.0F) {
        throw std::invalid_argument("maximum_score_error must be finite and non-negative");
    }
    EvaluationReport report;
    const auto use_cpu = [&]() {
        report.agents = evaluate_cpu(agents);
        report.backend = BackendKind::Cpu;
        report.backend_name = "CPU reference";
    };

    if (backend == nullptr || agents.size() < options.minimum_gpu_batch) {
        use_cpu();
        return report;
    }
    try {
        const ComputeBackendInfo capabilities = backend->info();
        if (!capabilities.available || capabilities.maximum_agents == 0U) {
            use_cpu();
            return report;
        }

        // Device storage limits are per dispatch, not per world snapshot. Split a
        // large immutable batch into bounded contiguous chunks while preserving ID
        // order. If any chunk fails parity or the adapter throws, discard every
        // partial result and recompute the complete snapshot on the CPU.
        std::vector<AgentOutput> candidate;
        candidate.reserve(agents.size());
        bool valid = true;
        for (std::size_t offset = 0; offset < agents.size();) {
            const std::size_t count = std::min(
                capabilities.maximum_agents, agents.size() - offset);
            const std::span<const AgentInput> chunk(agents.data() + offset, count);
            const std::vector<AgentOutput> chunk_output = backend->evaluate(chunk);
            const std::vector<AgentOutput> reference = evaluate_cpu(chunk);
            if (chunk_output.size() != count) {
                valid = false;
                break;
            }
            for (std::size_t i = 0; i < count; ++i) {
                const AgentOutput& output = chunk_output[i];
                const AgentOutput& expected = reference[i];
                if (output.agent_id != chunk[i].agent_id
                    || !std::isfinite(output.desperation_index)
                    || output.desperation_index < 0.0F
                    || output.desperation_index > 1.0F
                    || std::abs(output.desperation_index - expected.desperation_index)
                        > options.maximum_score_error
                    || output.trauma_tier > 3U
                    || output.trauma_tier != expected.trauma_tier
                    || output.rumour_transmittable != expected.rumour_transmittable
                    || output.attribution_survives != expected.attribution_survives) {
                    valid = false;
                    break;
                }
            }
            if (!valid) break;
            candidate.insert(candidate.end(), chunk_output.begin(), chunk_output.end());
            offset += count;
        }
        if (!valid || candidate.size() != agents.size()) {
            report.gpu_fallback = true;
            use_cpu();
            return report;
        }
        report.agents = std::move(candidate);
        report.backend = BackendKind::Gpu;
        report.backend_name = capabilities.name.empty() ? "GPU backend" : capabilities.name;
        return report;
    } catch (...) {
        report.gpu_fallback = true;
        use_cpu();
        return report;
    }
}

} // namespace simreality::fluid
