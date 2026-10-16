"""Memory decay.

The spec's equation was:

    R = R_0 * e^(-lambda * t)
    lambda = lambda_base * (Mod_Age + Mod_Visibility - Mod_Trauma)

That second line is broken. Because the trauma term is *subtracted*, a strong
trauma value drives lambda negative, and negative lambda makes R *increase* with
time. Worked example from the spec's own table, cheapest possible case -- petty
theft (2.0), young adult (1.0), noon and clear (0.8):

    lambda = 0.01 * (1.0 + 0.8 - 2.0) = -0.002

A petty-theft memory would grow stronger the longer it went unmentioned. Same
collision hits armed assault from the other side, where the surviving positive
term makes a supposedly permanent memory decay nine times faster than baseline.

The fix is to make every factor a multiplier. Multiplication cannot go negative
as long as no factor is negative, so the sign bug is unrepresentable rather than
merely guarded against:

    lambda = lambda_base * Mod_Age * Mod_Visibility * DecayRate

This also reproduces the intended ordering exactly, because the spec's Trauma
column was already inverse (armed assault got the *small* 0.05 precisely because
small means "never fades"). Renaming it `DecayRate` makes that legible.

Second fix, on the curve rather than the constant. The spec wants witnessed armed
assault to lock into the database "never fully decaying", but a bare exponential
with any lambda > 0 reaches zero eventually -- at lambda = 0.0032/hr the shooting
is forgotten within a year. So the curve has a floor:

    R(t) = R_0 * (floor + (1 - floor) * e^(-lambda * t))

where `floor` comes from `model.RETENTION_FLOOR`. Armed assault settles at 85% of
its original impact; petty theft at 5%. Scaling by R_0 rather than adding a
constant keeps a *faint* memory of a violent act from inheriting permanence.

See docs/MATH-NOTES.md for the full derivation and the tuning table.
"""

from __future__ import annotations

from .model import (
    AGE_DECAY_MULTIPLIER,
    ActionTag,
    AgeBand,
    DECAY_RATE_MULTIPLIER,
    NPCMemory,
    RETENTION_FLOOR,
    Weather,
)
import math

#: Baseline decay rate, per in-game hour.
#:
#: Chosen by measurement, not by taste. `converse` re-bases the listener's
#: `initial_impact` to the speaker's *current* retention, so every hop compounds
#: the previous one's decay and a chain dies superlinearly. That compounding -- not
#: this constant -- is what makes the telephone effect work, which is why the
#: spec's literal 0.01 is not as inert as it first appears.
#:
#: Measured over a 16-NPC chain at 2 in-game hours per hop, ADULT witness
#: (age multiplier 1.2), theft memory:
#:
#:     lambda_base  last hop still named  last hop still alive
#:          0.08                 1                    4
#:          0.04                 2                    7
#:          0.02                 3                   10
#:          0.01                 4                   14
#:
#: 0.02 is the pick: the name stays exact for about three hops, so the people who
#: actually witnessed the crime can still accuse accurately, and the degraded
#: description survives ~10 hops, which is far enough to reach another district and
#: send a patrol after the wrong person. Raise it and rumours die before they
#: spread; lower it and nobody ever loses the name and the morph never happens.
#:
#: This is a tuning constant, not a physical one. Change it and re-run the chain
#: tests before touching anything else.
LAMBDA_BASE = 0.02


def visibility_modifier(game_hour: float, weather: Weather) -> float:
    """Structural data capture, from lighting and weather.

    Spec anchors: noon/clear = 0.8, midnight/heavy rain = 2.5. Modelled as
    (day vs night) x (weather) so every combination in between is defined.
    `game_hour` is absolute elapsed time; reduce it modulo 24 before checking daylight.
    """
    hour_of_day = game_hour % 24.0
    day_factor = 0.8 if 6.0 <= hour_of_day < 18.0 else 1.5
    weather_factor = 1.0 if weather is Weather.CLEAR else 2.5
    return day_factor * weather_factor


def decay_constant(
    age_band: AgeBand,
    action_tag: ActionTag,
    game_hour: float,
    weather: Weather,
    lambda_base: float | None = None,
) -> float:
    """Return lambda for one memory. Always >= 0 by construction.

    `game_hour` is when the memory was *formed* -- low light at the time of the
    event is what limits the initial encoding.

    `lambda_base` defaults to None rather than to `LAMBDA_BASE` deliberately. A
    default of `lambda_base=LAMBDA_BASE` binds the value at definition time, so
    rebinding `decay.LAMBDA_BASE` at runtime silently does nothing and every
    tuning pass measures an unchanged curve. Resolving it here keeps the constant
    honest, and passing it explicitly still works for per-experiment overrides.
    """
    if lambda_base is None:
        lambda_base = LAMBDA_BASE
    return (
        lambda_base
        * AGE_DECAY_MULTIPLIER[age_band]
        * visibility_modifier(game_hour, weather)
        * DECAY_RATE_MULTIPLIER[action_tag]
    )


def retention_after(
    memory: NPCMemory,
    age_band: AgeBand,
    current_hour: float,
    weather: Weather,
    lambda_base: float | None = None,
) -> float:
    """Retention of `memory` at `current_hour`.

    Pure and time-independent: always computed from the original R_0 and the
    original timestamp, never by integrating step to step. Stepwise accumulation
    would drift, and drift makes a memory's strength depend on how often the
    background thread happened to wake up.
    """
    if memory.timestamp_hour > current_hour:
        return memory.initial_impact

    lam = decay_constant(
        age_band, memory.action_tag, memory.timestamp_hour, weather, lambda_base
    )
    elapsed = current_hour - memory.timestamp_hour
    floor = RETENTION_FLOOR[memory.action_tag]
    return memory.initial_impact * (floor + (1.0 - floor) * math.exp(-lam * elapsed))


def sweep(
    memories: list[NPCMemory],
    age_band: AgeBand,
    current_hour: float,
    weather: Weather,
    lambda_base: float | None = None,
) -> list[NPCMemory]:
    """Advance a whole witness's memory table. Returns a new list.

    This is the per-in-game-hour background-thread tick from the vision doc.
    Callers holding many NPCs should batch this across all of them rather than
    per-NPC, since it is pure and cheap.
    """
    return [
        m.decayed_to(retention_after(m, age_band, current_hour, weather, lambda_base))
        for m in memories
    ]