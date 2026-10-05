"""Core data records for the simulation.

These structs are the contract. They contain no engine types and no behaviour, so
the C++ port is a near-mechanical translation of this file.

Note on `ActionTag`: the spec called the decay modifier `Modifier_Trauma` and
listed values like 2.0 for petty theft and 0.05 for armed assault. Those numbers
are *inverse* to trauma -- bigger number means the memory fades FASTER, so the
armed-assault value is the small one because that memory never fades. Keeping the
spec's name would make every call site read backwards. Renamed to
`decay_rate_multiplier`; see docs/MATH-NOTES.md for the equation fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import math


# --------------------------------------------------------------------------
# Tags and enums
# --------------------------------------------------------------------------


class ActionTag(str, Enum):
    """What the witness saw the target do."""

    INTERACTION_POLITE = "Interaction.Polite"
    CRIME_THEFT = "Crime.Theft"
    CRIME_ASSAULT = "Crime.Assault"
    CRIME_ARMED_ASSAULT = "Crime.ArmedAssault"
    CRIME_VANDALISM = "Crime.Vandalism"


#: How fast a memory of this action fades. 1.0 is baseline. Values above 1.0 mean
#: "routine, forget quickly"; values below 1.0 mean "this burns in and never fully
#: goes away". Derived directly from the spec's Modifier_Trauma column, with its
#: subtractive-sign bug corrected (see docs/MATH-NOTES.md).
DECAY_RATE_MULTIPLIER: dict[ActionTag, float] = {
    ActionTag.INTERACTION_POLITE: 4.0,
    ActionTag.CRIME_VANDALISM: 2.5,
    ActionTag.CRIME_THEFT: 2.0,
    ActionTag.CRIME_ASSAULT: 0.4,
    ActionTag.CRIME_ARMED_ASSAULT: 0.05,
}


#: Fraction of the original impact a memory settles at as t -> infinity.
#:
#: This exists because the spec asks for two things its own equation cannot both
#: deliver: "witnessed armed assault ... never fully decaying", plus a single
#: exponential `R = R_0 * e^(-lambda t)`. Any lambda > 0 drives R to zero
#: eventually, so a permanent memory is unreachable. Even a tiny lambda = 0.0032/hr
#: erases a shooting after a year, which contradicts the stated intent outright.
#:
#: Fix is a two-term curve -- the memory fades toward a permanent scar instead of
#: toward nothing:
#:
#:     R(t) = R_0 * (floor + (1 - floor) * e^(-lambda * t))
#:
#: Armed assault keeps 85% of its impact forever, so a witness to a shooting can
#: still name the shooter years later. Petty theft keeps nothing and fades to zero,
#: because the spec grants permanence only to the violent cases -- giving theft a
#: small floor would make every shoplifting rumour immortal, which floods the city
#: with stale whispers. Scaling by `R_0` rather than adding a constant matters: a
#: *faint* memory of a violent act must not inherit permanence from its tag.
RETENTION_FLOOR: dict[ActionTag, float] = {
    ActionTag.INTERACTION_POLITE: 0.0,
    ActionTag.CRIME_VANDALISM: 0.0,
    ActionTag.CRIME_THEFT: 0.0,
    ActionTag.CRIME_ASSAULT: 0.4,
    ActionTag.CRIME_ARMED_ASSAULT: 0.85,
}


class AgeBand(str, Enum):
    YOUNG_ADULT = "YoungAdult"
    ADULT = "Adult"
    SENIOR = "Senior"


#: Relative importance of age to decay rate. Same multiplier family as
#: `DECAY_RATE_MULTIPLIER` -- bigger means forgets faster, so the senior value is
#: 1.4 because elders let go of a face more readily than a young adult does.
AGE_DECAY_MULTIPLIER: dict[AgeBand, float] = {
    AgeBand.YOUNG_ADULT: 1.0,
    AgeBand.ADULT: 1.2,
    AgeBand.SENIOR: 1.4,
}


class Weather(str, Enum):
    CLEAR = "Clear"
    RAIN = "HeavyRain"


class TraumaLevel(int, Enum):
    """Behavioural override tier. See docs/DESIGN-NOTES.md."""

    BASELINE = 0
    ANXIOUS = 1
    PARANOID = 2
    VIGILANTE = 3


# --------------------------------------------------------------------------
# Description -- a distribution, not a point value
# --------------------------------------------------------------------------


@dataclass
class Description:
    """A rumour's physical description of a target.

    The spec sketched this as a bare `FVector` of (Height, Clothing Color,
    Masked). That cannot work, because a rumour is formed by *merging* what
    several NPCs remember, and two witnesses who each saw "about 1.8m" do not
    average to a sharper 1.8m -- they average to a *wider* range of guesses. So
    every trait carries its own uncertainty, and hearing the same rumour twice
    narrows that uncertainty.

    Consequence: a rumour heard once stays vague ("tall-ish, maybe dark
    jacket"), while one corroborated three times sharpens into a usable
    description. That is the mechanic from the vision doc, expressed as data.
    """

    height_m: float = 0.0
    height_uncertainty_m: float = 0.35

    #: Jacket colour -> weight. Weights need not sum to 1.
    jacket_colour_weights: dict[str, float] = field(default_factory=dict)

    masked: bool = False
    masked_confidence: float = 0.0

    #: How many independent witnesses have contributed. Drives uncertainty decay:
    #: `height_uncertainty_m` is already the error of the *mean* of those
    #: witnesses, so corroboration is what tightens it. Without a count, repeated
    #: hears cannot be distinguished from a single bad estimate.
    #:
    #: Last field on purpose. It is bookkeeping, not part of the physical profile,
    #: and inserting a defaulted field mid-list silently corrupts every positional
    #: constructor -- `Description(1.8, 0.3, {...}, False, 0.9)` would land the
    #: colour dict in this slot and a bool in `jacket_colour_weights`, with no
    #: error raised. Keep new fields at the end, or keyword-only after the first cut.
    observations: int = 1

    @property
    def jacket_confidence(self) -> float:
        """0.0 = no idea what they wore, 1.0 = certain.

        Normalised weight of the leading colour. A uniform draw across N
        colours gives 1/N, so this reads as "how much better than guessing".
        """
        total = sum(self.jacket_colour_weights.values())
        if total <= 0.0:
            return 0.0
        return max(self.jacket_colour_weights.values()) / total

    def merge(self, other: "Description", speaker_fidelity: float = 1.0) -> "Description":
        """Fold another witness's version into this one.

        `speaker_fidelity` scales the other witness's contribution: a speaker who
        is barely retaining the memory should barely move the rumour.

        Uncertainty is the error of the *mean* of all contributing witnesses. For
        independent measurements that is sqrt(sum(sigma_i^2 * n_i^2)) / n_total --
        so a second witness genuinely halves the error instead of the naive
        quadrature sum, which would *widen* it and punish corroboration.

        `masked_confidence` is certainty in the *decision*, not P(masked), and the
        two are combined with an agreement-aware operator rather than an average.
        Averaging is the obvious choice and it is wrong: pooling two identical
        estimates returns that same estimate, so two witnesses who both clearly saw
        a masked face would leave the rumour exactly as unsure as one witness did,
        and corroboration would be inert. Agreement instead compounds toward
        certainty (`c + (1-c)*c_other`) and contradiction collapses it
        (`c * (1-c_other)`), which is the standard fuzzy-conjunction reading and
        gives the "maybe masked" middle state the vision doc needs.
        """
        n_self = self.observations
        n_other = max(1, int(round(other.observations * speaker_fidelity)))

        mean = (self.height_m * n_self + other.height_m * n_other) / (n_self + n_other)
        total_ss = (
            self.height_uncertainty_m**2 * n_self**2
            + other.height_uncertainty_m**2 * n_other**2
        )
        spread = math.sqrt(total_ss) / (n_self + n_other)

        colours = dict(self.jacket_colour_weights)
        for name, weight in other.jacket_colour_weights.items():
            colours[name] = colours.get(name, 0.0) + weight * speaker_fidelity

        if self.masked == other.masked:
            if self.masked:
                certainty = self.masked_confidence + (1.0 - self.masked_confidence) * (
                    other.masked_confidence * speaker_fidelity
                )
            else:
                inv = self.masked_confidence + (1.0 - self.masked_confidence) * (
                    other.masked_confidence * speaker_fidelity
                )
                certainty = 1.0 - inv
        else:
            certainty = self.masked_confidence * (1.0 - other.masked_confidence * speaker_fidelity)

        p_masked = min(1.0, max(0.0, certainty))
        masked = p_masked >= 0.5

        return Description(
            height_m=mean,
            height_uncertainty_m=spread,
            observations=n_self + n_other,
            jacket_colour_weights=colours,
            masked=masked,
            masked_confidence=p_masked,
        )

    def describe(self) -> str:
        """Render for an LLM prompt or a police dispatch log."""
        bits = []
        if self.height_uncertainty_m >= 0.25:
            bits.append("tall-ish" if self.height_m >= 1.75 else "average height")
        elif self.height_uncertainty_m >= 0.1:
            bits.append(f"about {self.height_m:.2f}m")
        else:
            bits.append(f"{self.height_m:.2f}m")

        if self.jacket_confidence > 0.6:
            top = max(self.jacket_colour_weights, key=self.jacket_colour_weights.get)
            bits.append(f"{top} jacket")
        elif self.jacket_colour_weights:
            bits.append("dark jacket" if self.jacket_confidence < 0.4 else "jacket")

        if self.masked_confidence > 0.7:
            bits.append("masked")
        elif self.masked_confidence > 0.3:
            bits.append("maybe masked")

        return ", ".join(bits)


# --------------------------------------------------------------------------
# Memory
# --------------------------------------------------------------------------


@dataclass
class NPCMemory:
    """One witnessed event, as retained by one witness.

    Field names follow the spec's `FNPCMemory` for easy comparison. `retention`
    is `RetentionScore`, and `initial_impact` is `InitialImpact` / R_0.
    """

    witness_id: str
    target_entity_id: str | None
    initial_impact: float
    retention: float
    timestamp_hour: float
    action_tag: ActionTag
    description: Description

    @property
    def is_actionable(self) -> bool:
        """Can this memory still produce a usable lead?

        Below threshold the witness cannot name who they saw -- only what they
        looked like. This single predicate is the whole telephone effect.
        """
        return self.retention >= TELEPHONE_THRESHOLD and self.target_entity_id is not None

    def decayed_to(self, retention: float) -> "NPCMemory":
        return replace(self, retention=max(0.0, min(1.0, retention)))


#: Below this retention a witness can no longer pass on a name or an ID.
TELEPHONE_THRESHOLD = 0.6


@dataclass
class NPC:
    """A citizen or officer."""

    entity_id: str
    age_band: AgeBand = AgeBand.ADULT
    moral_shackle: float = 0.8
    desperation_index: float = 0.0
    trauma_level: TraumaLevel = TraumaLevel.BASELINE

    #: Accumulated personal trauma -- what was done to this person, as opposed to
    #: what is happening around them. Fed by `trauma.absorb`, unwound by
    #: `trauma.relieve`. Kept separate from `desperation_index` because the two
    #: drive different tiers; see `trauma.py`.
    personal_stress: float = 0.0

    memories: list[NPCMemory] = field(default_factory=list)

    def remember(self, memory: NPCMemory) -> None:
        self.memories.append(memory)

    def memories_of(self, target_entity_id: str) -> list[NPCMemory]:
        return [m for m in self.memories if m.target_entity_id == target_entity_id]


@dataclass
class District:
    """A neighbourhood. Owns its own environmental pressure.

    The stress fields are state, not configuration: `districts.tick_day` moves
    them once per in-game day. The brief gives DI a "daily cycle" but defines no
    dynamics for its inputs, which left every district permanently frozen and
    meant the city-scar trigger in 2.B could never fire from an unchanging city.
    """

    district_id: str
    overpopulation: float = 0.3
    supply_shortage: float = 0.3
    weather_severity: float = 0.0
    local_corruption: float = 0.2
    security_presence: float = 0.5

    #: Head-count dynamics. `overpopulation` is derived from these rather than set
    #: directly, so crowding and hunger stay causally linked.
    population: int = 30
    capacity: int = 100

    #: City-scar state -- see `districts.py`. Persists across days.
    days_above_critical: int = 0
    days_recovering: int = 0
    scar_active: bool = False
    scar_intensity: float = 0.0

    residents: list[NPC] = field(default_factory=list)