"""Differential checks between the Python reference and portable C++ decay core.

The test compiles a tiny C++ probe with the same compiler family used for the
portable core, then compares numeric results to the Python implementation.
It skips cleanly on machines without a C++ compiler.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from simreality import decay
from simreality.model import ActionTag, AgeBand, Description, NPCMemory, Weather

ROOT = Path(__file__).resolve().parents[1]
CPP_PROBE = ROOT / "cpp" / "tests" / "DecayDifferentialProbe.cpp"


@unittest.skipUnless(shutil.which("c++") or shutil.which("g++") or shutil.which("clang++"),
                     "C++ compiler is not installed")
class TestCppPythonDecayParity(unittest.TestCase):
    def test_retention_vectors_match(self):
        compiler = shutil.which("c++") or shutil.which("g++") or shutil.which("clang++")
        with tempfile.TemporaryDirectory(prefix="simreality-decay-") as temp:
            executable = Path(temp) / ("decay_probe.exe" if os.name == "nt" else "decay_probe")
            subprocess.run(
                [compiler, "-std=c++20", "-O2", "-I", str(ROOT / "cpp" / "include"),
                 str(CPP_PROBE), str(ROOT / "cpp" / "src" / "Decay.cpp"),
                 "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            completed = subprocess.run(
                [str(executable)], check=True, capture_output=True, text=True
            )

        actual = [float(line) for line in completed.stdout.splitlines()]
        cases = [
            (AgeBand.YOUNG_ADULT, ActionTag.CRIME_THEFT, 12.0, 36.0, Weather.CLEAR),
            (AgeBand.ADULT, ActionTag.CRIME_ARMED_ASSAULT, 0.0, 8760.0, Weather.CLEAR),
            (AgeBand.SENIOR, ActionTag.CRIME_ASSAULT, 22.0, 70.0, Weather.RAIN),
            (AgeBand.ADULT, ActionTag.INTERACTION_POLITE, 6.0, 18.0, Weather.CLEAR),
            (AgeBand.YOUNG_ADULT, ActionTag.CRIME_VANDALISM, 23.0, 47.0, Weather.RAIN),
        ]
        expected = []
        for age, tag, formed, now, weather in cases:
            memory = NPCMemory(
                witness_id="probe-witness", target_entity_id="probe-target",
                initial_impact=0.73, retention=0.73,
                timestamp_hour=formed, action_tag=tag, description=Description(),
            )
            expected.append(decay.retention_after(memory, age, now, weather))

        self.assertEqual(len(actual), len(expected))
        for index, (cpp_value, python_value) in enumerate(zip(actual, expected)):
            with self.subTest(vector=index):
                self.assertTrue(math.isfinite(cpp_value))
                self.assertAlmostEqual(cpp_value, python_value, delta=1e-12)


if __name__ == "__main__":
    unittest.main()
