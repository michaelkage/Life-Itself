#include "simreality/Fluid.h"

#include <algorithm>
#include <bit>
#include <cmath>
#include <limits>
#include <stdexcept>
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

void validate(const std::vector<AgentInput>& agents) {
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

void append_f32_le(std::vector<std::uint8_t>& bytes, float value) {
    const std::uint32_t bits = std::bit_cast<std::uint32_t>(value);
    bytes.push_back(static_cast<std::uint8_t>(bits & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 8U) & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 16U) & 0xffU));
    bytes.push_back(static_cast<std::uint8_t>((bits >> 24U) & 0xffU));
}

} // namespace

std::vector<std::uint8_t> pack_agents(const std::vector<AgentInput>& agents) {
    validate(agents);
    if (agents.size() > std::numeric_limits<std::size_t>::max() / kAgentInputStride) {
        throw std::length_error("agent batch is too large to pack");
    }
    std::vector<std::uint8_t> bytes;
    bytes.reserve(agents.size() * kAgentInputStride);
    for (const AgentInput& a : agents) {
        append_f32_le(bytes, a.x);
        append_f32_le(bytes, a.y);
        append_f32_le(bytes, a.moral_shackle);
        append_f32_le(bytes, a.personal_stress);
        append_f32_le(bytes, a.overpopulation);
        append_f32_le(bytes, a.supply_shortage);
        append_f32_le(bytes, a.weather_severity);
        append_f32_le(bytes, a.local_corruption);
        append_f32_le(bytes, a.rumour_retention);
        append_f32_le(bytes, a.speaker_fidelity);
        append_f32_le(bytes, a.description_uncertainty);
        append_f32_le(bytes, a.target_known ? 1.0F : 0.0F);
    }
    return bytes;
}

std::vector<AgentOutput> evaluate_cpu(const std::vector<AgentInput>& agents) {
    validate(agents);
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

} // namespace simreality::fluid
