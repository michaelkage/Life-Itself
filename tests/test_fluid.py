import struct
import unittest
from simreality.fluid import (AGENT_INPUT_STRIDE, DispatchLimits, FluidAgentInput,
                              evaluate_cpu, pack_agents, plan_dispatches)

class FluidBatchTests(unittest.TestCase):
    def make_agent(self, **overrides):
        values = dict(agent_id="npc-1", x=12.5, y=-4.0, moral_shackle=0.8,
            personal_stress=0.2, overpopulation=0.3, supply_shortage=0.4,
            weather_severity=0.1, local_corruption=0.2, rumour_retention=0.7,
            speaker_fidelity=0.8, description_uncertainty=0.25, target_known=True)
        values.update(overrides)
        return FluidAgentInput(**values)

    def test_gpu_layout_is_three_vec4_values_per_agent(self):
        packed = pack_agents((self.make_agent(),))
        self.assertEqual(len(packed), AGENT_INPUT_STRIDE)
        self.assertEqual(struct.unpack("<12f", packed)[:4], (12.5, -4.0, 0.8, 0.2))
        self.assertEqual(struct.unpack("<12f", packed)[-1], 1.0)

    def test_batch_layout_scales_to_target_population(self):
        agents = tuple(self.make_agent(agent_id=f"npc-{i}") for i in range(500_000))
        self.assertEqual(len(pack_agents(agents)), 500_000 * AGENT_INPUT_STRIDE)

    def test_pressure_and_trauma_reference_equations(self):
        result = evaluate_cpu((self.make_agent(overpopulation=1.0, supply_shortage=1.0,
            weather_severity=1.0, local_corruption=1.0, personal_stress=0.1),))[0]
        self.assertAlmostEqual(result.desperation_index, 1.0)
        self.assertEqual(result.trauma_tier, 3)

    def test_rumour_transmission_and_attribution_thresholds(self):
        cases = ((0.7, True, True, True), (0.59, True, True, False),
                 (0.01, True, False, False), (0.01, False, False, False),
                 (0.02, False, True, False))
        for retention, known, transmittable, attributed in cases:
            result = evaluate_cpu((self.make_agent(rumour_retention=retention,
                target_known=known),))[0]
            self.assertEqual(result.rumour_transmittable, transmittable)
            self.assertEqual(result.attribution_survives, attributed)

    def test_invalid_batch_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            pack_agents((self.make_agent(), self.make_agent()))
        with self.assertRaises(ValueError):
            self.make_agent(personal_stress=1.1)
        with self.assertRaises(TypeError):
            self.make_agent(target_known=1)

    def test_dispatch_planner_respects_device_limits_and_stable_order(self):
        ranges = plan_dispatches(500_000, DispatchLimits(10_000, 64))
        self.assertTrue(ranges)
        self.assertEqual(ranges[0].agent_offset, 0)
        self.assertEqual(ranges[-1].agent_offset + ranges[-1].agent_count, 500_000)
        self.assertEqual(sum(item.agent_count for item in ranges), 500_000)
        for index, item in enumerate(ranges):
            self.assertLessEqual(item.agent_count, 10_000)
            self.assertLessEqual(item.workgroup_count, 64)
            if index + 1 < len(ranges):
                self.assertEqual(item.agent_count % 256, 0)
            self.assertEqual(item.workgroup_count, (item.agent_count + 255) // 256)

    def test_dispatch_planner_handles_small_devices_and_empty_batches(self):
        ranges = plan_dispatches(250, DispatchLimits(100, 1))
        self.assertEqual([item.agent_count for item in ranges], [100, 100, 50])
        self.assertEqual([item.workgroup_count for item in ranges], [1, 1, 1])
        self.assertEqual(plan_dispatches(0, DispatchLimits(100, 1)), ())

    def test_dispatch_planner_respects_storage_binding_byte_limits(self):
        input_limited = plan_dispatches(900, DispatchLimits(
            1000, 64, maximum_input_buffer_bytes=48 * 300,
            maximum_output_buffer_bytes=16 * 1000))
        self.assertEqual([item.agent_count for item in input_limited],
                         [256, 256, 256, 132])
        output_limited = plan_dispatches(900, DispatchLimits(
            1000, 64, maximum_input_buffer_bytes=48 * 1000,
            maximum_output_buffer_bytes=16 * 300))
        self.assertEqual([item.agent_count for item in output_limited],
                         [256, 256, 256, 132])
        with self.assertRaises(ValueError):
            plan_dispatches(1, DispatchLimits(
                100, 1, maximum_input_buffer_bytes=0))

    def test_dispatch_planner_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            plan_dispatches(1, DispatchLimits(100, 0))
        with self.assertRaises(ValueError):
            plan_dispatches(1, DispatchLimits(100, 1, 0))
        with self.assertRaises(TypeError):
            plan_dispatches(True, DispatchLimits(100, 1))
        with self.assertRaises(ValueError):
            plan_dispatches(1, DispatchLimits(100, 1, 128))

    def test_f32_overflow_is_rejected_by_packer(self):
        with self.assertRaises((OverflowError, struct.error)):
            pack_agents((self.make_agent(x=1e100),))

if __name__ == "__main__":
    unittest.main()
