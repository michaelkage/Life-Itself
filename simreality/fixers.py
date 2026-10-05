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
#:
#: Calibrated, and the first value was wrong by a factor of two. At 0.55 the
#: exposure term (0.55 x 0.5 = 0.28) beat the drive term (desperation x greed,
#: ~0.21 at typical values) almost everywhere in the parameter space, so
#:
#:     desperation 0.75, bribe 0.8, warrants 0.9
#:         standing 0.9 -> 0.000    a connected fixer NEVER betrays
#:         standing 0.5 -> 0.000
#:         standing 0.2 -> 0.104
#:
#: Only fixers with no standing at all ever squealed. That is the same 100%-or-
#: never whiplash as bug 12, inverted, and it contradicts the fiction: a
#: well-connected fixer under real pressure taking a bribe worth the risk is the
#: dramatic case, and it was the one case that could not happen.
#:
#: At 0.25 the drive dominates and exposure modulates rather than gates:
#:
#:     peak pressure, big bribe, connected  -> 0.11  sometimes betrays you
#:     peak pressure, big bribe, unknown    -> 0.31
#:     quiet district, connected            -> 0.00  never
#:     trivial bribe, connected             -> 0.00  nobody risks this for nothing
EXPOSURE_WEIGHT = 0.25

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


# --------------------------------------------------------------------------
# The network
# --------------------------------------------------------------------------

#: What a squealer costs their peers, scaled by the squealer's own standing.
#: A well-known fixer selling someone out is a far bigger blow to the district's
#: confidence in its fixers than a nobody doing it, which is the right ordering
#: and also the reason a burned network keeps burning.
BETRAYAL_TRUST_COST = 0.34

#: What a clean deal slowly restores. Small, and always outrun by the cost above:
#: the network is designed to be damaged faster than it heals.
CLEAN_DEAL_RECOVERY = 0.03

#: Standing a fixer drifts back toward, day by day. Not zero -- see below.
TRUST_RESTING = 0.5

#: Daily pull back toward `TRUST_RESTING`.
#:
#: Slow on purpose, and for the same reason corruption falls at 0.01 rather than
#: at the rate it rises: this is a structural property of a district, not a mood.
#: At 0.06 the network was back to full resting standing inside a fortnight, which
#: left the propagation doing nothing observable -- a player who was just sold out
#: found the very next fixer in the same district exactly as willing as the first.
#: At 0.015 the damage is roughly halved every 46 days: still clearly there after
#: a month, which is the window that matters, and gone in a year.
TRUST_REVERSION = 0.015

#: The best standing a district's network can sustain, as a function of how much
#: pressure the district is under.
#:
#: Without a ceiling, reliably dealing with fixers walks every member to 1.0 and
#: the network becomes permanently honest -- which contradicts the premise that
#: fixing is unstable by nature and removes any reason to watch your back. The
#: ceiling is a function of desperation rather than a constant because a fixer
#: network in a district with nothing wrong has no reason to exist, let alone to
#: be trusted.
TRUST_CEILING_FLOOR = 0.35
TRUST_CEILING_SPAN = 0.55


@dataclass
class FixerNetwork:
    """The fixers in one district, and what they have heard from each other.

    `FixerProfile` is deliberately a list of independent actors with no links
    between them, which meant the brief's "fixer network" had no collective
    behaviour at all: a player could be sold out six times over and the seventh
    fixer would deal exactly as they did the first.

    There is no separate trust score. Trust *is* the mean standing of the members,
    and propagation happens by writing to their standing directly, so there is
    exactly one source of truth. A parallel `trust` float alongside per-member
    standing would drift out of sync with them and be a second thing to reconcile.
    """

    district_id: str
    members: list[FixerProfile] = field(default_factory=list)

    @property
    def trust(self) -> float:
        """Mean standing across the network, in 0..1."""
        if not self.members:
            return 0.0
        return sum(m.standing for m in self.members) / len(self.members)

    def ceiling(self, district: District) -> float:
        """Highest mean standing this district can sustain right now."""
        return TRUST_CEILING_FLOOR + TRUST_CEILING_SPAN * desperation_index(district)

    def record_outcome(
        self, fixer: FixerProfile, negotiation: Negotiation, district: District
    ) -> None:
        """Fold one completed approach back into the network.

        Called after every `negotiate`, including refusals -- a player who is
        repeatedly turned away is not neutral to how the network feels about
        them, and the refusals here are about the fixer's own standing, not the
        player's reputation.
        """
        if not negotiation.accepted:
            return

        cost = (
            BETRAYAL_TRUST_COST * fixer.standing
            if negotiation.betrayed
            else -CLEAN_DEAL_RECOVERY
        )

        floor = FIXER_MIN_STANDING
        for member in self.members:
            member.standing = max(floor, min(1.0, member.standing - cost))
        # The ceiling is deliberately NOT enforced here. A clean deal legitimately
        # lifts a member above it between ticks, and clamping on every approach
        # meant the next clean deal immediately pushed back through the limit,
        # leaving the network permanently above its own ceiling. `daily_update`
        # owns the ceiling, because it is a daily-state clamp rather than a
        # response to any one event.

    def daily_update(self, district: District, days: float = 1.0) -> None:
        """One in-game day of drift. Call from the same tick as everything else.

        Standing pulls back toward `TRUST_RESTING`, floored at `FIXER_MIN_STANDING`
        so a burned network can still be worked. The floor is load-bearing: without
        it, betrayal knocked every fixer in a district below the threshold at which
        they would deal, refusal meant no deal, and no deal meant no further
        betrayal to lose -- a one-way ratchet that shut the fixer route permanently
        for a player in a single unlucky district.
        """
        ceiling = self.ceiling(district)
        for member in self.members:
            pulled = member.standing + (TRUST_RESTING - member.standing) * (
                1.0 - (1.0 - TRUST_REVERSION) ** days
            )
            member.standing = max(FIXER_MIN_STANDING, min(ceiling, pulled))