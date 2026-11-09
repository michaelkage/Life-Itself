"""SRE-Fluid: deterministic, GPU-compatible batches for high-volume agent scoring."""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct
from typing import Iterable

AGENT_INPUT_FLOATS = 12
AGENT_INPUT_STRIDE = AGENT_INPUT_FLOATS * 4
AGENT_OUTPUT_FLOATS = 4
AGENT_OUTPUT_STRIDE = AGENT_OUTPUT_FLOATS * 4
DI_WEIGHTS = (1.2, 1.5, 0.8, 1.1)
DI_WEIGHT_TOTAL = sum(DI_WEIGHTS)
RUMOUR_ATTRIBUTION_THRESHOLD = 0.6
RUMOUR_FLOOR_ATTRIBUTED = 0.05
RUMOUR_FLOOR_UNATTRIBUTED = 0.01

def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    try:
        valid = math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be finite")

def _unit(value, name):
    _finite(value, name)
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")

@dataclass(frozen=True)
class FluidAgentInput:
    """One compact agent work item; all non-coordinate channels are normalised."""
    agent_id: str
    x: float
    y: float
    moral_shackle: float
    personal_stress: float
    overpopulation: float
    supply_shortage: float
    weather_severity: float
    local_corruption: float
    rumour_retention: float
    speaker_fidelity: float
    description_uncertainty: float
    target_known: bool

    def __post_init__(self):
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        _finite(self.x, "x")
        _finite(self.y, "y")
        for name in ("moral_shackle", "personal_stress", "overpopulation",
                     "supply_shortage", "weather_severity", "local_corruption",
                     "rumour_retention", "speaker_fidelity", "description_uncertainty"):
            _unit(getattr(self, name), name)
        if not isinstance(self.target_known, bool):
            raise TypeError("target_known must be bool")

@dataclass(frozen=True)
class FluidAgentOutput:
    agent_id: str
    desperation_index: float
    trauma_tier: int
    rumour_transmittable: bool
    attribution_survives: bool

def pack_agents(agents: Iterable[FluidAgentInput]) -> bytes:
    """Pack 3 vec4<f32> values per agent (48-byte stride)."""
    items = tuple(agents)
    if any(not isinstance(item, FluidAgentInput) for item in items):
        raise TypeError("agents must contain FluidAgentInput values")
    ids = [item.agent_id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("agent IDs must be unique within a batch")
    packed = bytearray()
    for a in items:
        packed.extend(struct.pack("<12f", a.x, a.y, a.moral_shackle, a.personal_stress,
            a.overpopulation, a.supply_shortage, a.weather_severity, a.local_corruption,
            a.rumour_retention, a.speaker_fidelity, a.description_uncertainty,
            1.0 if a.target_known else 0.0))
    return bytes(packed)

def evaluate_cpu(agents: Iterable[FluidAgentInput]) -> tuple[FluidAgentOutput, ...]:
    """Reference implementation for the WGSL one-invocation-per-agent kernel."""
    items = tuple(agents)
    pack_agents(items)
    results = []
    for a in items:
        pressure = (a.overpopulation * 1.2 + a.supply_shortage * 1.5
                    + a.weather_severity * 0.8 + a.local_corruption * 1.1) / DI_WEIGHT_TOTAL
        pressure = min(1.0, max(0.0, pressure))
        personal = 2 if a.personal_stress >= 0.45 else (1 if a.personal_stress >= 0.10 else 0)
        environmental = 3 if pressure >= 0.90 else (2 if pressure >= 0.75 else (1 if pressure >= 0.60 else 0))
        attributed_input = a.target_known and a.rumour_retention >= RUMOUR_ATTRIBUTION_THRESHOLD
        floor = RUMOUR_FLOOR_ATTRIBUTED if attributed_input else RUMOUR_FLOOR_UNATTRIBUTED
        transmittable = a.rumour_retention > floor
        results.append(FluidAgentOutput(a.agent_id, pressure, max(personal, environmental),
                                        transmittable, transmittable and attributed_input))
    return tuple(results)
