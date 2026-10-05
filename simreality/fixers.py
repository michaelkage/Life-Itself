"""Reputation, fixers, and betrayal.

Brief section 4.B. The mechanic is good -- intermediaries, not a bribe menu, and
fixers who act on their own incentives -- but the betrayal rule as written is
broken in a way that is not obvious from the prose.

**Betrayal is strictly dominant, so it must happen 100% of the time.** Compare the
fixer's two outcomes:

    loyalty   -> keeps the bribe
    betrayal  -> keeps the bribe, PLUS their own warrants are cleared,
                 PLUS the player is removed as a live witness

Nothing is lost by betraying. The brief attaches no cost, no exposure risk, no
reputational damage among peers, and no chance of being caught. Under those
payoffs a rational fixer always betrays, so a "might betray" that is really
"always betrays" would arrive as scripted ambushes with no warning, and the
player would learn the fixers are not a route at all.

Fixed by giving betrayal something to lose. Three counters, in order of weight:

    desperation    the brief's own trigger. Peak pressure does raise the odds.
    greed           bribe size relative to what the fixer stands to gain
    exposure        how protected the fixer is. A well-connected fixer risks
                    everything by squealing, and knows it.

`negotiate` returns a single atomic outcome. Splitting "did they take the money"
from "did they squeal" into two decisions lets a caller observe the payment and
then skip the betrayal, which is the one thing this mechanic must not allow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ecosystem import desperation_index
from .model import District, NPC

#: Local standing of the player in a district. Below this, fixers decline.
REPUTATION_FLOOR = 0.35

#: Weight of a bribe against the fixer's own outstanding warrants in deciding
#: whether the money is worth the risk of taking it.
BRIBE_WEIGHT = 0.45

#: What squealing costs a fixer. Scaled by how well connected they are: a fixer
#: with standing is exactly the kind who gets noticed, and who loses the most by
#: being noticed.
EXPOSURE_WEIGHT = 0.55

#: Standing below which a fixer will not deal at all.
FIXER_MIN_STANDING = 0.2


@dataclass
class Negotiation:
    """The outcome of one approach. Exactly one of these can happen."""

    accepted: bool
    bribe_paid: bool
    betrayed: bool
    reason: str
    squeal_filed: bool = False


@dataclass
class FixerProfile:
    """A fixer in a district. Their incentives are their own."""

    entity_id: str
    district_id: str
    standing: float = 0.5
    #: Outstanding warrants the fixer wants cleared by trading the player up.
    warrants: float = 0.0
    bribes_accepted: number = 0.0
    dealings: list[str] = field(default_factory=list)

    def desperation(self, district: District) -> float:
        return desperation_index(district)


def bribe_greed(bribe: float, warrants: float) -> float:
    """How tempting a bribe is, against what clearing the fixer gets them.

    Saturates toward 1 as the bribe grows, and shrinks if the fixer has little to
    gain. An expensive fixer with deep warrants wants the deal; a cheap one with
    clean books does not.
    """
    return (BRIBE_WEIGHT * bribe) / max(1e-9, BRIBE_WEIGHT * bribe + warrants)


def betrayal_probability(
    fixer_desperation: float,
    bribe: float,
    warrants: float,
    standing: float,
) -> float:
    """Chance the fixer takes the money and files the tip. In 0..1.

    At zero standing and peak desperation this approaches 1 -- the brief's
    "might betray" at its most aggressive. At high standing it falls away,
    because squealing costs them more than the bribe pays.
    """
    return max(0.0, min(1.0, fixer_desperation * bribe_greed(bribe, warrants) - EXPOSURE_WEIGHT * standing))


def willingness_to_deal(reputation: float, fixer: FixerProfile, district: District) -> tuple[bool, str]:
    """Will this fixer work with this player? Returns (willing, reason)."""
    if fixer.standing < FIXER_MIN_STANDING:
        return False, "not established enough to risk dealing"
    if reputation < REPUTATION_FLOOR:
        return False, f"reputation {reputation:.2f} below the floor of {REPUTATION_FLOOR}"
    if desperation_index(district) < 0.3:
        return False, "district is too stable for me to be seen helping anyone"
    return True, "deal"


def negotiate(
    player_id: str,
    fixer: FixerProfile,
    district: District,
    bribe: float,
    reputation: float,
    rng: float,
) -> Negotiation:
    """One approach to one fixer.

    `rng` is a caller-supplied uniform sample, injected so the outcome is
    deterministic and testable. The outcome is atomic: a fixer who betrays has
    taken the money *and* filed the tip. There is no path that pays without
    risking the ambush.
    """
    willing, reason = willingness_to_deal(reputation, fixer, district)

    if not willing:
        return Negotiation(
            accepted=False,
            bribe_paid=False,
            betrayed=False,
            reason=reason,
        )

    p_betray = betrayal_probability(
        fixer.desperation(district), bribe, warrants=fixer.warrants, standing=fixer.standing
    )

    if rng < p_betray:
        fixer.bribes_accepted += bribe
        fixer.dealings.append("betrayed")
        return Negotiation(
            accepted=True,
            bribe_paid=True,
            betrayed=True,
            reason=(
                "took the money and filed an anonymous tip to clear their own "
                "warrants -- clean police are on their way"
            ),
            squeal_filed=True,
        )

    fixer.bribes_accepted += bribe
    fixer.dealings.append("dealt")
    return Negotiation(
        accepted=True,
        bribe_paid=True,
        betrayed=False,
        reason="took the deal and kept quiet",
    )


def known_betrayers(fixers: list[FixerProfile]) -> list[str]:
    """Fixers who have already sold someone out. The player learns this the hard way."""
    return [f.entity_id for f in fixers if "betrayed" in f.dealings]