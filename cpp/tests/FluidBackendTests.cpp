#include "simreality/Fluid.h"

#include <cassert>
#include <cmath>
#include <stdexcept>
#include <string>
#include <vector>

using namespace simreality::fluid;

namespace {
class ReferenceBackend final : public ComputeBackend {
public:
    bool available{true};
    bool throw_on_evaluate{false};
    float score_offset{0.0F};
    std::uint8_t trauma_override{255U};

    [[nodiscard]] ComputeBackendInfo info() const override {
        return {"reference test backend", available, 10000U};
    }

    [[nodiscard]] std::vector<AgentOutput> evaluate(
        const std::vector<AgentInput>& agents) override {
        if (throw_on_evaluate) throw std::runtime_error("simulated adapter failure");
        auto outputs = evaluate_cpu(agents);
        for (auto& output : outputs) {
            output.desperation_index += score_offset;
            if (trauma_override != 255U) output.trauma_tier = trauma_override;
        }
        return outputs;
    }
};

AgentInput sample() {
    AgentInput agent;
    agent.agent_id = "npc-differential";
    agent.personal_stress = 0.45F;
    agent.overpopulation = 0.4F;
    agent.supply_shortage = 0.5F;
    agent.weather_severity = 0.3F;
    agent.local_corruption = 0.2F;
    agent.rumour_retention = 0.8F;
    agent.target_known = true;
    return agent;
}
} // namespace

int main() {
    const std::vector<AgentInput> batch{sample()};
    ReferenceBackend backend;
    EvaluationOptions options;
    options.minimum_gpu_batch = 1U;

    const auto accepted = evaluate_with_fallback(batch, &backend, options);
    assert(accepted.backend == BackendKind::Gpu);
    assert(!accepted.gpu_fallback);

    backend.score_offset = 0.00002F;
    const auto score_mismatch = evaluate_with_fallback(batch, &backend, options);
    assert(score_mismatch.backend == BackendKind::Cpu);
    assert(score_mismatch.gpu_fallback);

    backend.score_offset = 0.0F;
    backend.trauma_override = 1U;
    const auto tier_mismatch = evaluate_with_fallback(batch, &backend, options);
    assert(tier_mismatch.backend == BackendKind::Cpu);
    assert(tier_mismatch.gpu_fallback);

    backend.trauma_override = 255U;
    backend.throw_on_evaluate = true;
    const auto adapter_failure = evaluate_with_fallback(batch, &backend, options);
    assert(adapter_failure.backend == BackendKind::Cpu);
    assert(adapter_failure.gpu_fallback);

    bool rejected_negative_tolerance = false;
    try {
        options.maximum_score_error = -0.1F;
        (void)evaluate_with_fallback(batch, &backend, options);
    } catch (const std::invalid_argument&) {
        rejected_negative_tolerance = true;
    }
    assert(rejected_negative_tolerance);

    bool rejected_nan_tolerance = false;
    try {
        options.maximum_score_error = std::nanf("");
        (void)evaluate_with_fallback(batch, &backend, options);
    } catch (const std::invalid_argument&) {
        rejected_nan_tolerance = true;
    }
    assert(rejected_nan_tolerance);
    return 0;
}
