"""Local reputation, derived from evidence.

The brief refers to "local reputation" as a thing fixers read before dealing
(brief 4.B) and as a thing that makes Anxious citizens suspicious of players
(brief 4.A). It never defines where it comes from, and the obvious stub -- a
float on the criminal file -- is wrong in three separate ways, all of which were
found by running the numbers rather than by reading the prose.

**A stored score is global; the brief's is local.** A float on the criminal file
means one crime in D4 makes fixers in D9 refuse you, having never heard of it. The
brief's word is *local*, and it matters: a city where everyone knows everything
about you is a different game from one where your reputation is a rumour that has
to reach you through the same gossip network as everything else.

**A stored score drifts.** It has to be written by something, and the systems that
would write it do not exist. It sat at its `0.5` default forever, which put every
player permanently just above the `0.35` floor that fixers check.

**Deriving it from witness memories alone produces the custody paradox.** Reputation
computed purely from present evidence collapses when the evidence decays:

    player robs a shop, five witnesses, all actionable  -> reputation 0.20
    arrested, convicted, sentenced to 30 days
    30 days later: 0 of 5 witness memories still actionable  -> reputation 1.00

The player is in prison with a conviction and is locally respectable, because the
only thing holding their reputation down was the same rumour that convicted them.
The memory model quietly erased the social cost of the crime it had just proven.

Fixed with two independent terms. A conviction is a court record and outlives the
rumour that produced it; it decays toward a floor, never to zero, because old
convictions stay discoverable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .justice import SEVERITY, CriminalFile
from .model import NPCMemory

#: A single fully-remembered offence of that severity costs this much standing.
#: Combined across distinct offences as `1 - prod(1 - weight)`, so several
#: separate acts compound without ever exceeding 1.0.
ACCUSATION_GAIN = 0.7

#: How much of a conviction survives once it is old. Never zero: a conviction is a
#: public record, and public records do not disappear, they just stop being
#: current news.
RECORD_FLOOR = 0.15

#: Daily decay of conviction salience *after* the sentence has been served.
#: Half-life of roughly 34 days -- slow, and sticky for the same reason
#: corruption is. A district's opinion of you should not reset over a fortnight.
RECORD_DECAY_PER_DAY = 0.98


@dataclass(frozen=True)
class ReputationProfile:
    """Reputation in one district, and what it was derived from.

    Split out so a debugger or an in-game UI can show *why* a fixer is refusing,
    rather than just a number.
    """

    reputation: float
    accusation_penalty: float
    record_penalty: float

    @property
    def source(self) -> str:
        if self.record_penalty >= self.accusation_penalty:
            return "record"
        return "accusation"

    @property
    def clean(self) -> bool:
        return self.accusation_penalty <= 0.0 and self.record_penalty <= 0.0


def _accusation_weight(memory: NPCMemory) -> float:
    """Social cost of one witnessed act, in 0..1.

    Scaled by retention because a witness who can barely still name the player
    is not a reliable voice for the district.
    """
    return SEVERITY.get(memory.action_tag, 0.0) * memory.retention * ACCUSATION_GAIN


def accusation_penalty(memories: list[NPCMemory], player_id: str) -> float:
    """What the district currently believes about the player, as a penalty.

    Only *actionable* memories count. A rumour that has decayed below the
    telephone threshold no longer names anybody, so it cannot name them here
    either -- otherwise a player's social standing would be propped up by
    accusations too vague to charge them with, which is the same defect
    `justice` was fixed for.

    Deduplicated per offence, keeping the strongest single witness. Five people
    witnessing one shoplifting is one act, not five; counting them separately
    would compound a single incident into a reputation collapse, which is the
    corroboration bug from `justice.file_from_memories` repeating one layer up.
    """
    strongest: dict = {}
    for memory in memories:
        if memory.target_entity_id != player_id or not memory.is_actionable:
            continue
        weight = _accusation_weight(memory)
        if weight > strongest.get(memory.action_tag, 0.0):
            strongest[memory.action_tag] = weight

    remaining = 1.0
    for weight in strongest.values():
        remaining *= 1.0 - weight
    return 1.0 - remaining


def record_penalty(criminal_file: CriminalFile | None, current_day: int) -> float:
    """What the court's record says about the player, as a penalty.

    Holds at full strength for the length of the sentence -- the conviction is
    fresh news while it is happening -- then decays toward `RECORD_FLOOR`.

    Only the most recent conviction is scored. Convictions are cumulative in the
    file and should compound in principle, but summing them made a player with
    three old theft convictions permanently unemployable, which turns the fixer
    route off permanently rather than expensively. Recency is the honest signal.
    """
    if criminal_file is None:
        return 0.0

    conviction = criminal_file.most_recent_conviction()
    if conviction is None:
        return 0.0

    days_served = max(0, current_day - conviction.convicted_on_day)
    past_sentence = max(0.0, float(days_served) - conviction.sentence_days)
    salience = RECORD_FLOOR + (1.0 - RECORD_FLOOR) * (RECORD_DECAY_PER_DAY**past_sentence)
    return conviction.severity * salience


def local_reputation(
    memories: list[NPCMemory],
    player_id: str,
    criminal_file: CriminalFile | None = None,
    current_day: int = 0,
) -> ReputationProfile:
    """Reputation in the district whose residents hold `memories`, in 0..1.

    The two terms are combined with `max`, not a sum. One act produces both a
    witness memory *and* a conviction for the same offence, so summing them
    punished the player twice for a single crime -- and the clamp at 1.0 turned
    that double count into an unrecoverable reputation of zero.
    """
    accusation = accusation_penalty(memories, player_id)
    record = record_penalty(criminal_file, current_day)
    penalty = max(accusation, record)
    return ReputationProfile(
        reputation=max(0.0, min(1.0, 1.0 - penalty)),
        accusation_penalty=accusation,
        record_penalty=record,
    )
