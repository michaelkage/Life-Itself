"""SRE-Fluid: deterministic, GPU-compatible batches for high-volume agent scoring."""
from __future__ import annotations
from dataclasses import dataclass
import math
import struct
import sys
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
WORKGROUP_SIZE = 256

@dataclass(frozen=True)
class DispatchLimits:
    """Limits reported by a compute device for one dispatch."""
    maximum_agents: int
    maximum_workgroups_per_dimension: int
    workgroup_size: int = WORKGROUP_SIZE
    maximum_input_buffer_bytes: int = sys.maxsize
    maximum_output_buffer_bytes: int = sys.maxsize

@dataclass(frozen=True)
class DispatchRange:
    """Contiguous agent range and its one-dimensional workgroup count."""
    agent_offset: int
    agent_count: int
    workgroup_count: int

def plan_dispatches(agent_count: int, limits: DispatchLimits) -> tuple[DispatchRange, ...]:
    """Plan bounded, stable-order dispatches without querying a GPU.

    Intermediate chunks are aligned to full workgroups where possible. The
    final chunk may be partial and must use the shader's invocation bounds guard.
    """
    for name, value in (
        ("agent_count", agent_count),
        ("maximum_agents", limits.maximum_agents),
        ("maximum_workgroups_per_dimension", limits.maximum_workgroups_per_dimension),
        ("workgroup_size", limits.workgroup_size),
        ("maximum_input_buffer_bytes", limits.maximum_input_buffer_bytes),
        ("maximum_output_buffer_bytes", limits.maximum_output_buffer_bytes),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0 or (name != "agent_count" and value == 0):
            raise ValueError(f"{name} is outside its valid range")
    if limits.workgroup_size != WORKGROUP_SIZE:
        raise ValueError("workgroup_size must match the compiled WGSL shader")
    if limits.maximum_workgroups_per_dimension > sys.maxsize // limits.workgroup_size:
        raise ValueError("dispatch workgroup limit overflows the supported size")
    storage_capacity = min(sys.maxsize // AGENT_INPUT_STRIDE,
                           sys.maxsize // AGENT_OUTPUT_STRIDE)
    safe_capacity = min(
        limits.maximum_agents,
        limits.maximum_workgroups_per_dimension * limits.workgroup_size,
        limits.maximum_input_buffer_bytes // AGENT_INPUT_STRIDE,
        limits.maximum_output_buffer_bytes // AGENT_OUTPUT_STRIDE,
        storage_capacity,
    )
    chunk_capacity = (
        (safe_capacity // limits.workgroup_size) * limits.workgroup_size
        if safe_capacity >= limits.workgroup_size else safe_capacity
    )
    ranges = []
    offset = 0
    while offset < agent_count:
        count = min(chunk_capacity, agent_count - offset)
        workgroups = (count + limits.workgroup_size - 1) // limits.workgroup_size
        ranges.append(DispatchRange(offset, count, workgroups))
        offset += count
    return tuple(ranges)

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
