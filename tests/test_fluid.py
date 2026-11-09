import struct
import unittest
from simreality.fluid import AGENT_INPUT_STRIDE, FluidAgentInput, evaluate_cpu, pack_agents

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
                 (0.05, True, False, False), (0.01, False, False, False),
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

    def test_f32_overflow_is_rejected_by_packer(self):
        with self.assertRaises((OverflowError, struct.error)):
            pack_agents((self.make_agent(x=1e100),))

if __name__ == "__main__":
    unittest.main()
