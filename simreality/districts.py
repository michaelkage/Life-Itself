"""District macro-dynamics and city scars.

Two gaps in the brief, both about time.

**The DI inputs never move.** Section 1.C says every citizen computes DI "on
their daily cycle", but no growth, decay, or reversion rate is given for
overpopulation, supply shortage, corruption, or weather. A district is therefore
frozen: the daily cycle recomputes the identical number forever. Nothing in the
game can deteriorate, and section 2.B's city scars -- which trigger on sustained
critical DI -- could never fire against a city that never changes.

Fixed by giving each input a rate. Two shapes, chosen per input:

    mean-reverting   pulls toward an equilibrium. Supply shortage, weather.
    ratcheting       rises readily, falls grudgingly. Corruption.

The asymmetry on corruption is the important one. Corruption that decayed as
readily as it grew would mean any district could be cleaned up by arresting the
right people, which removes the structural premise of the setting.

**City scars flicker.** Section 2.B triggers when DI "stays critical for more
than three in-game days", with no definition of critical and no way back. A
strict `>` test on a district hovering near the mark flips the whole city
between clean and ruined on alternate days, and every material, every audio
sub-mix, and every police posture would strobe with it.

Fixed with hysteresis -- two thresholds, not one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ecosystem import desperation_index
from .model import District

# --------------------------------------------------------------------------
# Input dynamics
# --------------------------------------------------------------------------

#: How fast overpopulation tracks the population/capacity ratio, per day. Slow:
#: people move districts over weeks, not overnight.
OVERPOPULATION_REVERSION = 0.15

#: Share of a supply shock still felt the next day. Weather-driven scarcity does
#: not clear overnight because the shelves are already empty.
SUPPLY_PERSISTENCE = 0.75

#: Base equilibrium for supply shortage at zero crowding.
SUPPLY_BASELINE = 0.15

#: Extra shortage attributable to crowding.
SUPPLY_CROWDING_WEIGHT = 0.7

#: Corruption rises toward its equilibrium quickly and falls slowly.
CORRUPTION_RISE = 0.12
CORRUPTION_FALL = 0.01

#: How much corruption follows from desperation and absent policing.
#:
#: Calibrated so the achievable DI range actually reaches the top of the model.
#: At 0.35 corruption equilibrated near 0.7 and DI plateaued at 0.93 even with
#: 4x overpopulation, zero policing, and a permanent storm -- below
#: SCAR_ENTER_DI = 0.85 in most weather, and permanently below the 0.95 paragon
#: shackle, so a district could never fully collapse and the top of the moral
#: range was unreachable.
#:
#: Equilibrium DI by sustained weather, 4x overpopulation, no policing:
#:
#:     weather 0.0 -> 0.78   no scars: scarcity alone does not ruin a district
#:     weather 0.6 -> 0.91   scars
#:     weather 1.0 -> 1.00   even the paragon breaks
CORRUPTION_PRESSURE = 0.8
CORRUPTION_SECURITY_WEIGHT = 0.4

#: Weather mean-reverts to clear.
WEATHER_REVERSION = 0.4


def target_overpopulation(district: District) -> float:
    """Crowding implied by head-count against capacity."""
    if district.capacity <= 0:
        return 1.0
    return max(0.0, min(1.0, district.population / district.capacity))


def target_supply_shortage(district: District) -> float:
    """Shelves empty from crowding, weather, and low baseline stocking."""
    return max(
        0.0,
        min(
            1.0,
            SUPPLY_BASELINE
            + SUPPLY_CROWDING_WEIGHT * district.overpopulation
            + 0.3 * district.weather_severity,
        ),
    )


def target_corruption(district: District) -> float:
    """Corruption follows desperation and thin policing, not the reverse."""
    pressure = desperation_index(district)
    policing_gap = max(0.0, 1.0 - district.security_presence)
    return max(0.0, min(1.0, CORRUPTION_PRESSURE * pressure + CORRUPTION_SECURITY_WEIGHT * policing_gap))


def evolve_inputs(district: District, weather_severity: float) -> None:
    """Advance the environmental inputs by one in-game day.

    Mutates `district` in place. `weather_severity` is the day's observed weather,
    supplied from outside because weather is global, not a property of a district.
    """
    district.weather_severity += (
        weather_severity - district.weather_severity
    ) * WEATHER_REVERSION

    crowd_target = target_overpopulation(district)
    district.overpopulation += (crowd_target - district.overpopulation) * OVERPOPULATION_REVERSION

    supply_target = target_supply_shortage(district)
    district.supply_shortage += (
        supply_target - district.supply_shortage
    ) * (1.0 - SUPPLY_PERSISTENCE)

    corruption_target = target_corruption(district)
    rate = CORRUPTION_RISE if corruption_target > district.local_corruption else CORRUPTION_FALL
    district.local_corruption += (corruption_target - district.local_corruption) * rate


# --------------------------------------------------------------------------
# City scars
# --------------------------------------------------------------------------

#: DI at which a district is considered to be failing. Entering here starts the
#: countdown.
SCAR_ENTER_DI = 0.85

#: DI at which a district is considered recovered. Deliberately well below
#: SCAR_ENTER_DI: the gap is the hysteresis band, and anything inside it holds
#: whatever state the district was already in.
SCAR_EXIT_DI = 0.60

#: Consecutive days above SCAR_ENTER_DI before the district visibly scars.
SCAR_DAYS_REQUIRED = 3

#: Days a district must stay below SCAR_EXIT_DI before the scars fade.
SCAR_RECOVERY_DAYS = 4

#: Per-day rate the visible scar intensity climbs and falls.
SCAR_RISE_RATE = 0.34
SCAR_FALL_RATE = 0.25


@dataclass(frozen=True)
class ScarState:
    """What the renderer and audio mixer read. Pure data, no engine types."""

    active: bool
    intensity: float
    days_above_critical: int
    desperation_index: float

    @property
    def boarded_windows(self) -> bool:
        """Brief 2.B: broken glass replaced with boards once a district scars."""
        return self.active and self.intensity > 0.3

    @property
    def derelict_facades(self) -> bool:
        """Concrete blending to dirt, trash, and cracked normals."""
        return self.intensity > 0.6

    @property
    def police_ignore_minor_offences(self) -> bool:
        """Corrupt, unwatched sectors stop pursuing small crimes."""
        return self.active


def update_scars(district: District) -> ScarState:
    """Advance scar state by one day. Mutates `district`.

    Call after `evolve_inputs`, so DI reflects today's state.
    """
    di = desperation_index(district)

    if di >= SCAR_ENTER_DI:
        district.days_above_critical += 1
        district.days_recovering = 0
    else:
        district.days_above_critical = 0
        if district.scar_active and di < SCAR_EXIT_DI:
            district.days_recovering += 1

    if not district.scar_active:
        if district.days_above_critical > SCAR_DAYS_REQUIRED:
            district.scar_active = True
    elif district.days_recovering >= SCAR_RECOVERY_DAYS:
        district.scar_active = False

    district.scar_intensity = max(
        0.0,
        min(
            1.0,
            district.scar_intensity
            + (SCAR_RISE_RATE if district.scar_active else -SCAR_FALL_RATE),
        ),
    )

    return ScarState(
        active=district.scar_active,
        intensity=district.scar_intensity,
        days_above_critical=district.days_above_critical,
        desperation_index=di,
    )


def tick_day(district: District, weather_severity: float = 0.0) -> ScarState:
    """One full in-game day: evolve inputs, re-score DI, update scars.

    The single entry point the daily cycle should call.
    """
    evolve_inputs(district, weather_severity)
    return update_scars(district)