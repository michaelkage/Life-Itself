#include "simreality/Fluid.h"

#include <cassert>
#include <cmath>
#include <limits>
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
    std::size_t maximum_workgroups_per_dimension{65535U};
    std::size_t workgroup_size{kWorkgroupSize};
    std::size_t evaluate_calls{0U};
    std::size_t throw_on_call{0U};
    float score_offset{0.0F};
    std::uint8_t trauma_override{255U};

    [[nodiscard]] ComputeBackendInfo info() const override {
        return {"reference test backend", available, maximum_agents,
            maximum_workgroups_per_dimension, workgroup_size};
    }

    [[nodiscard]] std::vector<AgentOutput> evaluate(
        std::span<const AgentInput> agents) override {
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
    const auto dispatches = plan_dispatches(500000U,
        DispatchLimits{10000U, 64U, kWorkgroupSize});
    assert(!dispatches.empty());
    std::size_t planned_agents = 0U;
    std::size_t expected_offset = 0U;
    for (std::size_t i = 0U; i < dispatches.size(); ++i) {
        const auto& range = dispatches[i];
        assert(range.agent_offset == expected_offset);
        assert(range.agent_count > 0U && range.agent_count <= 10000U);
        assert(range.workgroup_count > 0U && range.workgroup_count <= 64U);
        if (i + 1U < dispatches.size()) {
            assert(range.agent_count % kWorkgroupSize == 0U);
        }
        assert(range.workgroup_count
            == range.agent_count / kWorkgroupSize
                + (range.agent_count % kWorkgroupSize == 0U ? 0U : 1U));
        planned_agents += range.agent_count;
        expected_offset += range.agent_count;
    }
    assert(planned_agents == 500000U);
    assert(dispatches.front().agent_offset == 0U);
    assert(dispatches.back().agent_offset + dispatches.back().agent_count == 500000U);
    assert(plan_dispatches(0U, DispatchLimits{100U, 1U, kWorkgroupSize}).empty());

    const auto tiny_device = plan_dispatches(250U,
        DispatchLimits{100U, 1U, kWorkgroupSize});
    assert(tiny_device.size() == 3U);
    assert(tiny_device[0].agent_count == 100U);
    assert(tiny_device[1].agent_count == 100U);
    assert(tiny_device[2].agent_count == 50U);
    assert(tiny_device[0].workgroup_count == 1U);

    bool rejected_zero_dispatch_limit = false;
    try {
        (void)plan_dispatches(1U, DispatchLimits{100U, 0U, kWorkgroupSize});
    } catch (const std::invalid_argument&) {
        rejected_zero_dispatch_limit = true;
    }
    assert(rejected_zero_dispatch_limit);

    bool rejected_dispatch_overflow = false;
    try {
        (void)plan_dispatches(1U, DispatchLimits{
            100U, std::numeric_limits<std::size_t>::max(), 2U});
    } catch (const std::invalid_argument&) {
        rejected_dispatch_overflow = true;
    }
    assert(rejected_dispatch_overflow);

    const std::vector<AgentInput> batch{sample()};
    // Caller-owned upload memory can be reused over many simulation ticks.
    std::vector<std::uint8_t> retained_upload(batch.size() * kAgentInputStride, 0U);
    pack_agents_into(batch, retained_upload);
    const auto allocated_upload = pack_agents(batch);
    assert(retained_upload == allocated_upload);
    const auto decoded = unpack_outputs(batch, std::vector<std::uint8_t>{
        0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U,
        0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U});
    assert(decoded.size() == 1U && decoded[0].agent_id == batch[0].agent_id);

    bool rejected_short_upload = false;
    try {
        std::vector<std::uint8_t> too_small(kAgentInputStride - 1U);
        pack_agents_into(batch, too_small);
    } catch (const std::invalid_argument&) {
        rejected_short_upload = true;
    }
    assert(rejected_short_upload);

    BufferWorkspace workspace;
    auto first_buffers = workspace.prepare(batch.size());
    assert(first_buffers.input.size() == kAgentInputStride);
    assert(first_buffers.output.size() == kAgentOutputStride);
    pack_agents_into(batch, first_buffers.input);
    const auto* retained_input_address = first_buffers.input.data();
    const auto* retained_output_address = first_buffers.output.data();
    first_buffers.input[0] = 0xA5U;
    first_buffers.output[0] = 0x5AU;
    auto smaller_buffers = workspace.prepare(0U);
    assert(smaller_buffers.input.empty() && smaller_buffers.output.empty());
    auto reused_buffers = workspace.prepare(batch.size());
    assert(reused_buffers.input.data() == retained_input_address);
    assert(reused_buffers.output.data() == retained_output_address);
    assert(reused_buffers.input[0] == 0xA5U);
    assert(reused_buffers.output[0] == 0x5AU);
    assert(workspace.capacity_agents() >= batch.size());
    reused_buffers.output[0] = 0U;
    pack_agents_into(batch, reused_buffers.input);
    const auto workspace_decoded = unpack_outputs(batch, reused_buffers.output);
    assert(workspace_decoded.size() == batch.size());
    assert(workspace_decoded[0].agent_id == batch[0].agent_id);
    auto grown_buffers = workspace.prepare(100U);
    assert(grown_buffers.input.size() == 100U * kAgentInputStride);
    assert(grown_buffers.output.size() == 100U * kAgentOutputStride);
    assert(workspace.capacity_agents() >= 100U);

    bool rejected_workspace_overflow = false;
    try {
        (void)workspace.prepare(std::numeric_limits<std::size_t>::max());
    } catch (const std::length_error&) {
        rejected_workspace_overflow = true;
    }
    assert(rejected_workspace_overflow);

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

    // The dispatcher also obeys workgroup-count limits reported by the device,
    // even when its storage buffer could hold a much larger batch.
    backend.evaluate_calls = 0U;
    backend.throw_on_call = 0U;
    backend.maximum_agents = 1000U;
    backend.maximum_workgroups_per_dimension = 1U;
    backend.maximum_agents = 1000U;
    std::vector<AgentInput> dispatch_limited_batch;
    for (int i = 0; i < 600; ++i) {
        AgentInput item = sample();
        item.agent_id = "dispatch-npc-" + std::to_string(i);
        dispatch_limited_batch.push_back(item);
    }
    const auto dispatch_limited = evaluate_with_fallback(
        dispatch_limited_batch, &backend, options);
    assert(dispatch_limited.backend == BackendKind::Gpu);
    assert(dispatch_limited.agents.size() == dispatch_limited_batch.size());
    assert(backend.evaluate_calls == 3U);
    backend.maximum_workgroups_per_dimension = 65535U;
    backend.maximum_agents = 2U;

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
