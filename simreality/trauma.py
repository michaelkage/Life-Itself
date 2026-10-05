"""Trauma accumulation and behavioural tiers.

Brief section 4.A defines four tiers, and each row mixes a *personal* cause with
an *environmental* one:

    Level 1 Anxious     -- witnessed petty crime        / rising shortages
    Level 2 Paranoid    -- direct victim of theft       / high district hunger
    Level 3 Vigilante   -- total systemic collapse      / zero law presence

Read as a list of alternatives, one event is enough to reach the top tier: a
witness to a single armed assault carries `InitialImpact` 1.0, so a linear
impact-to-tier mapping puts them at Level 3 immediately. But Level 3 is defined
as *zero law presence* -- an environmental condition that one crime cannot
create. The comma-and-slash notation leaves it genuinely ambiguous whether the
two causes are alternatives or requirements.

Resolved by splitting the axes, because they are independent in the fiction:

    personal_stress  -- what happened TO this person, decays slowly
    desperation      -- what is happening AROUND them, from the district

Level 1 and 2 come from either axis. Level 3 requires *both*, because a person
with no law around them and nothing done to them is not a vigilante -- they are
fine. A person badly wronged in a functioning city is furious and helpless, not
armed.

Recovery: the brief calls Level 2 "semi-permanent", so stress relaxes rather than
resets. A victim does not forget being robbed, they stop being defined by it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ecosystem import distress_trauma
from .model import ActionTag, NPC, TraumaLevel

#: Stress added when WITNESSING an event, by tag. Deliberately well below the
#: victim figures -- watching a crime is not the same as having it done to you.
WITNESS_STRESS: dict[ActionTag, float] = {
    ActionTag.CRIME_ARMED_ASSAULT: 0.50,
    ActionTag.CRIME_ASSAULT: 0.30,
    ActionTag.CRIME_THEFT: 0.08,
    ActionTag.CRIME_VANDALISM: 0.04,
    ActionTag.INTERACTION_POLITE: 0.00,
}

#: Stress added when the event was committed AGAINST this NPC.
VICTIM_STRESS: dict[ActionTag, float] = {
    ActionTag.CRIME_ARMED_ASSAULT: 1.00,
    ActionTag.CRIME_ASSAULT: 0.60,
    ActionTag.CRIME_THEFT: 0.15,
    ActionTag.CRIME_VANDALISM: 0.08,
    ActionTag.INTERACTION_POLITE: 0.00,
}

#: Fraction of accumulated stress retained per in-game day.
#:
#: Half-life of ~23 days. Slow on purpose: the brief wants Level 2 to be
#: semi-permanent, so this is a long unwind rather than a reset. It is
#: multiplicative, so stress never goes negative and never stalls at a floor.
STRESS_RETAINED_PER_DAY = 0.97

#: Personal stress needed to reach each tier from a single axis. Caps at
#: Paranoid, which is what stops one bad day from producing a vigilante.
TIER_ANXIOUS = 0.10
TIER_PARANOID = 0.45


@dataclass(frozen=True)
class TraumaAssessment:
    """Why an NPC sits in their current tier."""

    level: TraumaLevel
    personal_stress: float
    desperation_index: float
    source: str

    @property
    def permanent(self) -> bool:
        """Level 3 is not a mood. It needs the environment to hold."""
        return self.level is TraumaLevel.VIGILANTE


def relieve(days: float, stress: float) -> float:
    """Relax accumulated stress over `days` in-game days.

    Multiplicative, so a long absence approaches zero without ever crossing it.
    """
    return stress * (STRESS_RETAINED_PER_DAY**days)


def absorb(npc: NPC, action_tag: ActionTag, *, was_victim: bool = False) -> float:
    """Add the stress from one event to `npc`. Returns the new total.

    Mutates `npc.personal_stress`. Repeated events compound, which is the whole
    point -- a run of burglaries does more damage than one.
    """
    table = VICTIM_STRESS if was_victim else WITNESS_STRESS
    npc.personal_stress = min(1.0, npc.personal_stress + table[action_tag])
    return npc.personal_stress


def personal_level(stress: float) -> TraumaLevel:
    """Tier attainable from personal experience alone. Caps at Paranoid."""
    if stress >= TIER_PARANOID:
        return TraumaLevel.PARANOID
    if stress >= TIER_ANXIOUS:
        return TraumaLevel.ANXIOUS
    return TraumaLevel.BASELINE


def assess(npc: NPC, desperation_index: float) -> TraumaAssessment:
    """Combine both axes into a tier. Whichever is worse wins.

    The asymmetry lives in `personal_level`, which caps at Paranoid -- that is what
    stops one bad day from producing a vigilante. The environment axis has no such
    cap, and should not: the brief's Level 3 behaviour is largely *civic*
    ("forms or joins localized protection rings, refuses to talk to law
    enforcement"), which is a collective response to absent law rather than a
    personal response to a single crime. A citizen in a lawless district who was
    never victimised absolutely does join a protection ring.

    So: environment alone can reach Vigilante. Personal experience alone cannot.
    """
    stress = npc.personal_stress
    from_person = personal_level(stress)
    # `distress_trauma` returns None when the district is still tolerable, which
    # is a real answer -- an honest person in a bad district is uncomfortable, not
    # paranoid -- so it is normalised to BASELINE rather than compared raw.
    from_world = distress_trauma(desperation_index) or TraumaLevel.BASELINE

    level = max(from_person, from_world, key=lambda t: t.value)
    source = (
        "environment" if from_world.value > from_person.value
        else "personal" if from_person.value > from_world.value
        else "both"
    )

    return TraumaAssessment(level, stress, desperation_index, source)


def daily_update(npc: NPC, desperation_index: float, days: float = 1.0) -> TraumaAssessment:
    """The brief's daily cycle: relax, re-assess, write the tier back."""
    npc.personal_stress = relieve(days, npc.personal_stress)
    result = assess(npc, desperation_index)
    npc.trauma_level = result.level
    return result