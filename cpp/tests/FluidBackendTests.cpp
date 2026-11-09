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
    std::size_t maximum_agents{10000U};
    std::size_t evaluate_calls{0U};
    std::size_t throw_on_call{0U};
    float score_offset{0.0F};
    std::uint8_t trauma_override{255U};

    [[nodiscard]] ComputeBackendInfo info() const override {
        return {"reference test backend", available, maximum_agents};
    }

    [[nodiscard]] std::vector<AgentOutput> evaluate(
        const std::vector<AgentInput>& agents) override {
        ++evaluate_calls;
        if (throw_on_evaluate || (throw_on_call != 0U && evaluate_calls == throw_on_call)) {
            throw std::runtime_error("simulated adapter failure");
        }
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

    // Large world snapshots are split into device-capacity chunks without
    // changing stable result order. A later chunk failure discards partial GPU
    // output and recomputes the complete snapshot on the CPU.
    backend.throw_on_evaluate = false;
    backend.evaluate_calls = 0U;
    backend.throw_on_call = 0U;
    backend.maximum_agents = 2U;
    std::vector<AgentInput> large_batch;
    for (int i = 0; i < 5; ++i) {
        AgentInput item = sample();
        item.agent_id = "npc-" + std::to_string(i);
        large_batch.push_back(item);
    }
    const auto chunked = evaluate_with_fallback(large_batch, &backend, options);
    assert(chunked.backend == BackendKind::Gpu);
    assert(chunked.agents.size() == large_batch.size());
    assert(backend.evaluate_calls == 3U);
    for (std::size_t i = 0; i < large_batch.size(); ++i) {
        assert(chunked.agents[i].agent_id == large_batch[i].agent_id);
    }

    backend.evaluate_calls = 0U;
    backend.throw_on_call = 2U;
    const auto partial_failure = evaluate_with_fallback(large_batch, &backend, options);
    assert(partial_failure.backend == BackendKind::Cpu);
    assert(partial_failure.gpu_fallback);
    assert(partial_failure.agents.size() == large_batch.size());
    assert(backend.evaluate_calls == 2U);

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
