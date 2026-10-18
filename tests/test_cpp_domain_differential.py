"""Cross-domain differential checks against the Python reference implementation."""
from __future__ import annotations

import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from simreality import districts, fixers, gossip, justice, reputation, trauma
from simreality.model import ActionTag, Description, District, NPC, NPCMemory
from simreality.gossip import Rumour
from simreality.fixers import FixerProfile

ROOT = Path(__file__).resolve().parents[1]
CPP_PROBE = ROOT / "cpp" / "tests" / "DomainDifferentialProbe.cpp"
COMPILER = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")


@unittest.skipUnless(COMPILER, "C++ compiler is not installed")
class TestCppPythonDomainParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="simreality-domains-")
        cls.executable = Path(cls.temp.name) / ("domain_probe.exe" if os.name == "nt" else "domain_probe")
        sources = sorted((ROOT / "cpp" / "src").glob("*.cpp"))
        subprocess.run(
            [COMPILER, "-std=c++20", "-O2", "-I", str(ROOT / "cpp" / "include"),
             str(CPP_PROBE), *(str(source) for source in sources), "-o", str(cls.executable)],
            check=True, capture_output=True, text=True,
        )
        completed = subprocess.run([str(cls.executable)], check=True, capture_output=True, text=True)
        cls.actual = {}
        for line in completed.stdout.splitlines():
            fields = line.split()
            cls.actual[fields[0]] = [float(value) for value in fields[1:]]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def assert_values_match(self, domain, expected, tolerance=1e-12):
        actual = self.actual[domain]
        self.assertEqual(len(actual), len(expected), domain)
        for index, (left, right) in enumerate(zip(actual, expected)):
            with self.subTest(domain=domain, field=index):
                self.assertTrue(math.isfinite(left))
                self.assertAlmostEqual(left, float(right), delta=tolerance)

    def test_gossip_propagation_matches(self):
        description = Description(
            height_m=1.82, height_uncertainty_m=0.2,
            jacket_colour_weights={"black": 0.8, "blue": 0.2}, observations=2,
        )
        memory = NPCMemory(
            witness_id="witness", target_entity_id="target", retention=0.8,
            initial_impact=0.8, action_tag=ActionTag.CRIME_THEFT, description=description,
        )
        first = gossip.retell(memory)
        self.assertIsNotNone(first)
        second = Rumour(
            action_tag=first.action_tag, target_entity_id="target",
            description=Description(
                height_m=1.78, height_uncertainty_m=0.2,
                jacket_colour_weights={"black": 0.5, "red": 0.5}, observations=2
            ),
            retention=0.6,
        )
        merged = first.corroborate(second)
        self.assert_values_match("gossip", [
            first.retention, first.is_attributable, merged.retention,
            merged.description.observations, merged.description.jacket_confidence,
        ])

    def test_district_dynamics_match(self):
        district = District(
            "D", overpopulation=0.55, supply_shortage=0.4, weather_severity=0.2,
            local_corruption=0.3, security_presence=0.25, population=80, capacity=100,
        )
        scar = districts.tick_day(district, 0.9)
        self.assert_values_match("district", [
            district.overpopulation, district.supply_shortage, district.weather_severity,
            district.local_corruption, scar.desperation_index, scar.intensity, scar.active,
        ])

    def test_trauma_matches(self):
        person = NPC("person")
        stress = trauma.absorb(person, ActionTag.CRIME_THEFT, was_victim=True)
        self.assert_values_match("trauma", [
            stress, trauma.relieve(3.0, stress),
            {"Baseline": 0, "Anxious": 1, "Paranoid": 2, "Vigilante": 3}[trauma.personal_level(stress).value],
            {"Baseline": 0, "Anxious": 1, "Paranoid": 2, "Vigilante": 3}[trauma.assess(person, 0.9).level.value],
        ])

    def test_justice_matches(self):
        memory = NPCMemory(
            witness_id="witness", target_entity_id="target", retention=0.8,
            initial_impact=0.8, action_tag=ActionTag.CRIME_THEFT,
        )
        charge = justice.charge_from_memory(memory)
        self.assert_values_match("justice", [
            charge.severity, charge.sentence(), charge.provable,
            justice.enforcement_probability(ActionTag.CRIME_THEFT, 0.9),
        ])

    def test_reputation_matches(self):
        memory = NPCMemory(
            witness_id="witness", target_entity_id="target", retention=0.8,
            initial_impact=0.8, action_tag=ActionTag.CRIME_THEFT,
        )
        profile = reputation.local_reputation([memory], "target")
        self.assert_values_match("reputation", [
            profile.reputation, profile.accusation_penalty, profile.record_penalty,
        ])

    def test_fixer_behavior_matches(self):
        district = District(
            "D", overpopulation=1.0, supply_shortage=1.0, weather_severity=1.0,
            local_corruption=1.0, security_presence=0.0,
        )
        fixer = FixerProfile("fixer", "D", standing=0.3, warrants=0.2)
        probability = fixers.betrayal_probability(
            fixers.desperation_index(district), 0.8, fixer.warrants, fixer.standing
        )
        outcome = fixers.negotiate("player", fixer, district, 0.8, 0.8, 0.1)
        self.assert_values_match("fixer", [
            probability, outcome.accepted, outcome.bribe_paid, outcome.betrayed,
            fixer.bribes_accepted,
        ])


if __name__ == "__main__":
    unittest.main()
