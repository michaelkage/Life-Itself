"""Macro-environmental desperation.

The spec's equation:

    DI = (Stress_Overpopulation * 1.2) + (Stress_SupplyShortage * 1.5)
       + (Stress_Weather * 0.8) + (Stress_LocalCorruption * 1.1)

With every stress normalised to 0..1, the weights sum to 4.60, so DI lands on a
0..4.60 scale. But `MoralShackle` was documented as 0.2..0.95. The two quantities
were being compared across a five-fold scale mismatch, which means:

    uniform stress 0.2  ->  DI = 0.92   flips every shackle below 0.92
    uniform stress 0.3  ->  DI = 1.38   flips everyone, including 0.95 paragons

Moderate pressure criminalised the entire city on day one, and the "career
criminal" and "fiercely honest citizen" ends of the shackle range were
indistinguishable. Fixed by dividing through by the weight sum so DI is 0..1 and
directly comparable to a shackle.

The weights are preserved as *relative* importance: supply shortage still bites
hardest, weather still least.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import District, NPC, TraumaLevel

#: Relative pressure of each factor. Normalised on read -- do not expect the sum.
DI_WEIGHTS: dict[str, float] = {
    "overpopulation": 1.2,
    "supply_shortage": 1.5,
    "weather_severity": 0.8,
    "local_corruption": 1.1,
}

#: Sum of the weights. Dividing by this is what puts DI on the same 0..1 scale as
#: `NPC.moral_shackle`.
DI_WEIGHT_TOTAL = sum(DI_WEIGHTS.values())


class IllegalBranch(str):
    """Behaviour unlocked once an NPC's shackle breaks."""

    SHOPLIFT = "Shoplift"
    CARGO_HIJACK = "CargoHijack"
    BRIBE_OFFICIAL = "BribeOfficial"
    EXTORT_NEIGHBOUR = "ExtortNeighbour"
    JOIN_SYNDICATE = "JoinSyndicate"


@dataclass(frozen=True)
class BehaviourDecision:
    """What an NPC does today, given pressure and shackle."""

    illegal: bool
    branch: str | None
    desperation_index: float
    moral_shackle: float

    @property
    def reason(self) -> str:
        if not self.illegal:
            return f"DI {self.desperation_index:.2f} <= shackle {self.moral_shackle:.2f}"
        return f"DI {self.desperation_index:.2f} > shackle {self.moral_shackle:.2f} -> {self.branch}"


def desperation_index(district: District) -> float:
    """Pressure on a district, normalised to 0..1."""
    raw = (
        district.overpopulation * DI_WEIGHTS["overpopulation"]
        + district.supply_shortage * DI_WEIGHTS["supply_shortage"]
        + district.weather_severity * DI_WEIGHTS["weather_severity"]
        + district.local_corruption * DI_WEIGHTS["local_corruption"]
    )
    return max(0.0, min(1.0, raw / DI_WEIGHT_TOTAL))


def evaluate(npc: NPC, district: District) -> BehaviourDecision:
    """Decide whether `npc` breaks today, and down which branch.

    The status flip is the spec's: standard lifestyle script (GoToWork,
    ReturnHome) is dropped and illegal branches are considered. Branch selection
    follows the two documented combinations.
    """
    di = desperation_index(district)
    if di <= npc.moral_shackle:
        return BehaviourDecision(False, None, di, npc.moral_shackle)

    if district.supply_shortage >= 0.6 and district.security_presence <= 0.4:
        # Hungry and unwatched. Steal from a shop, or take the whole shipment.
        branch = (
            IllegalBranch.CARGO_HIJACK
            if district.supply_shortage >= 0.8
            else IllegalBranch.SHOPLIFT
        )
    elif district.local_corruption >= 0.5 and district.overpopulation >= 0.5:
        # Everyone is bought and there is nowhere to go. Turn on neighbours, or
        # sell yourself to whoever already runs the street.
        branch = (
            IllegalBranch.JOIN_SYNDICATE
            if district.overpopulation >= 0.75
            else IllegalBranch.BRIBE_OFFICIAL
        )
    else:
        branch = IllegalBranch.EXTORT_NEIGHBOUR

    return BehaviourDecision(True, branch, di, npc.moral_shackle)


def distress_trauma(di: float) -> TraumaLevel | None:
    """Escalate a citizen's trauma tier from sustained environmental pressure.

    Spec's mapping, keyed on how far past the shackle the district sits. Returns
    None while the citizen is still inside their own tolerance -- an honest
    person in a bad district is uncomfortable, not paranoid.
    """
    if di >= 0.90:
        return TraumaLevel.VIGILANTE
    if di >= 0.75:
        return TraumaLevel.PARANOID
    if di >= 0.60:
        return TraumaLevel.ANXIOUS
    return None


def apply_district_pressure(district: District) -> list[tuple[NPC, BehaviourDecision]]:
    """Recompute every resident's DI and decide today's behaviour.

    Called on the daily cycle from the vision doc, not per frame.
    """
    di = desperation_index(district)
    results = []
    for npc in district.residents:
        npc.desperation_index = di
        decision = evaluate(npc, district)

        # Sustained pressure wears on everyone; a broken citizen wears out faster.
        if decision.illegal:
            tier = distress_trauma(di)
            if tier and tier > npc.trauma_level:
                npc.trauma_level = tier

        results.append((npc, decision))
    return results