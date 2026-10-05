"""Arrest, evidence, and the plea bargain.

Brief section 2.A describes the physical arrest chain and the LLM-driven
negotiation. The engine work is out of scope here; this module owns the part that
is arithmetic -- what can actually be charged, on what evidence, and what a plea
bargain is worth.

Two problems in the brief's own logic:

**An arrest can outrun its evidence.** Information reaches police through the
gossip network, and a rumour below the transmission threshold has already lost
the target's identity. The brief's police response already handles this
correctly: an unattributable rumour produces a *stop*, not a pursuit. But the
arrest loop then proceeds from the stop as though an arrest were equivalent, so
the player's file accumulates real charges against a predicate fact that names
nobody. A file with no provable act cannot carry an attempted-bribery charge, a
plea bargain, or a trial.

Fixed by separating the two things the brief runs together. `Stop` is a
suspicion with no charge behind it. `Arrest` requires either the player's own
confession on record, or a charge whose evidence survives `can_prove`.

**Corruption stacks until the legal system vanishes.** Corrupt districts "ignore
minor offences", and untreated that multiplies through: at corruption 0.9 only
10% of petty theft is policed, and if that then scales arrest odds as well, the
chance of any arrest is 0.01%. The city silently stops having a legal system.

Fixed by confining corruption to where the brief puts it. It suppresses
enforcement of *minor* offences and leaves serious violence at essentially full
strength, with a hard floor so a charge can always be brought. Police in a ruined
district stop caring about shoplifting; they do not stop caring about a shooting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gossip import Rumour
from .model import ActionTag, District, NPCMemory

#: Severity of each offence, 0..1. Drives sentencing and what corruption can buy.
SEVERITY: dict[ActionTag, float] = {
    ActionTag.INTERACTION_POLITE: 0.0,
    ActionTag.CRIME_VANDALISM: 0.20,
    ActionTag.CRIME_THEFT: 0.35,
    ActionTag.CRIME_ASSAULT: 0.70,
    ActionTag.CRIME_ARMED_ASSAULT: 1.00,
}

#: Below this severity, corruption suppresses enforcement. Above it, enforcement
#: is essentially unconditional.
MINOR_OFFENCE_CUTOFF = 0.45

#: Enforcement never falls below this, however corrupt the district. Without a
#: floor the offence class becomes un prosecutable at high corruption.
ENFORCEMENT_FLOOR = 0.12

#: Weight of each charge kind when several stack on one file.
CHARGE_STACKING = {
    "unwitnessed": 0.30,
    "single_witness": 0.70,
    "corroborated": 1.00,
    "confessed": 1.00,
}


@dataclass
class Charge:
    """One provable act attributed to the player."""

    action_tag: ActionTag
    evidence: str
    strength: float

    @property
    def severity(self) -> float:
        return SEVERITY[self.action_tag]

    @property
    def provable(self) -> bool:
        """Can this survive a public defender reading the file?

        Unwitnessed accusations do not. A rumour that never named anybody cannot
        be tried, so it can be filed as intelligence but not as a charge.
        """
        return self.evidence != "unwitnessed"

    def sentence(self) -> float:
        """Base custodial sentence in days."""
        return round(30.0 * self.severity * self.strength)


@dataclass(frozen=True)
class Conviction:
    """A proven offence, on the public record.

    Exists because a conviction outlives the rumour that produced it. See
    `reputation.record_penalty` -- without this, a player in custody becomes
    locally respectable as the witness memories decay, because the only thing
    holding their reputation down was the same evidence that convicted them.
    """

    action_tag: ActionTag
    convicted_on_day: int
    #: Custodial sentence actually imposed, in days. A conviction with a real
    #: sentence behind it stays legible far longer than a token one.
    sentence_days: float = 0.0

    @property
    def severity(self) -> float:
        return SEVERITY[self.action_tag]


@dataclass
class CriminalFile:
    """The player's record. Survives arrest, plea, and trial.

    Note there is no `reputation` field. Reputation was one, defaulting to 0.5,
    and nothing ever read it -- a stored score with no writer, which is the
    failure mode this whole layer was rebuilt to avoid. It is derived from
    evidence instead; see `reputation.local_reputation`.
    """

    player_id: str
    charges: list[Charge] = field(default_factory=list)
    confessions: list[ActionTag] = field(default_factory=list)
    convictions: list[Conviction] = field(default_factory=list)
    bribe_attempts: int = 0

    @property
    def severity_total(self) -> float:
        return sum(c.severity * c.strength for c in self.charges if c.provable)

    def sentence_if_convicted(self) -> float:
        return sum(c.sentence() for c in self.charges if c.provable)

    def provable_charges(self) -> list[Charge]:
        return [c for c in self.charges if c.provable]

    def is_prosecutable(self) -> bool:
        return bool(self.provable_charges())

    def most_recent_conviction(self) -> Conviction | None:
        if not self.convictions:
            return None
        return max(self.convictions, key=lambda c: c.convicted_on_day)


@dataclass(frozen=True)
class Stop:
    """Suspicion without a charge.

    The honest outcome of acting on a rumour that has lost its identity.
    """

    reason: str
    rumour: Rumour | None = None
    released: bool = True


@dataclass(frozen=True)
class Arrest:
    """A custody event. Only constructible when there is something to charge."""

    file: CriminalFile
    charge: Charge
    officer_entity_id: str
    district_id: str


def can_prove(memory: NPCMemory) -> bool:
    """Can a charge be built from this single witness?

    Requires an *actionable* memory: above threshold, and therefore still naming
    somebody. A memory that has decayed into a description is intelligence, not
    evidence.
    """
    return memory.is_actionable


def charge_from_memory(memory: NPCMemory) -> Charge:
    """Build a charge from one witness, or an unprovable placeholder.

    Always returns `single_witness` when provable. Corroboration needs to know
    there is a *second* witness, which this function cannot see -- scoring a lone
    sharp witness as corroborated because its retention happened to exceed 0.9
    meant two agreeing witnesses and one confident witness produced identical
    files. Promotion to corroborated happens in `file_from_memories`.

    The placeholder exists so the file can record that something was reported --
    an unresolved report is still information about the player -- without letting
    it become prosecutable.
    """
    if can_prove(memory):
        return Charge(
            memory.action_tag, "single_witness", CHARGE_STACKING["single_witness"]
        )
    return Charge(memory.action_tag, "unwitnessed", CHARGE_STACKING["unwitnessed"])


def file_from_memories(
    player_id: str,
    memories: list[NPCMemory],
) -> CriminalFile:
    """Assemble a file from every witness who saw the player.

    Corroboration is per-action: two witnesses to the same act strengthen it to
    full weight rather than stacking into two separate charges, which would
    double-count a single incident.
    """
    by_action: dict[ActionTag, list[NPCMemory]] = {}
    for memory in memories:
        if memory.target_entity_id != player_id:
            continue
        by_action.setdefault(memory.action_tag, []).append(memory)

    criminal_file = CriminalFile(player_id=player_id)
    for action, witnesses in by_action.items():
        best = max(witnesses, key=lambda m: m.retention)
        charge = charge_from_memory(best)
        if len(witnesses) >= 2 and charge.provable:
            charge = Charge(action, "corroborated", CHARGE_STACKING["corroborated"])
        criminal_file.charges.append(charge)
    return criminal_file


def convict(
    criminal_file: CriminalFile,
    action_tag: ActionTag,
    current_day: int,
    sentence_days: float,
) -> Conviction:
    """Record a proven offence against the player.

    The charge stays on the file as well; the conviction is a separate, longer-
    lived fact. A charge is "police think you did this", a conviction is "a court
    found you did", and only the second one should follow you around for years.
    """
    record = Conviction(
        action_tag=action_tag,
        convicted_on_day=current_day,
        sentence_days=sentence_days,
    )
    criminal_file.convictions.append(record)
    return record


def register_bribe_attempt(criminal_file: CriminalFile) -> CriminalFile:
    """Brief 4.B: offering a bribe to an officer is itself an offence.

    Filed unconditionally, and *never* softened by district corruption. An
    officer who can be bought is precisely why bribing one cannot be allowed to
    work -- so this charge is the one thing corruption does not touch.
    """
    criminal_file.bribe_attempts += 1
    criminal_file.charges.append(
        Charge(ActionTag.CRIME_THEFT, "confessed", CHARGE_STACKING["single_witness"])
    )
    return criminal_file


def enforcement_probability(action_tag: ActionTag, corruption: float) -> float:
    """Chance a given offence is acted on at all, given local corruption.

    Suppression applies only below `MINOR_OFFENCE_CUTOFF`. Serious violence stays
    at nearly full strength, and `ENFORCEMENT_FLOOR` guarantees a charge can
    always be brought.
    """
    severity = SEVERITY[action_tag]
    if severity <= 0.0:
        return 1.0
    if severity >= MINOR_OFFENCE_CUTOFF:
        return max(1.0 - 0.1 * corruption, ENFORCEMENT_FLOOR)
    suppressed = 1.0 - corruption
    return max(suppressed, ENFORCEMENT_FLOOR)


def consequence_for(
    action_tag: ActionTag,
    criminal_file: CriminalFile,
    district: District,
    officer_entity_id: str,
    corruption: float,
    rng: float,
) -> Stop | Arrest | None:
    """Resolve one offence into nothing, a stop, or an arrest.

    `rng` is a caller-supplied uniform sample in 0..1, injected rather than drawn
    here so the whole legal layer stays deterministic and testable.

    Three outcomes, and the middle one is the one the brief's prose skipped:

        None    the offence was not acted on. Corruption may have suppressed it.
        Stop    a patrol acted, but nothing on the file can carry a charge. The
                citizen is searched, found innocent, and released.
        Arrest  a patrol acted and there is a provable charge to bring.

    This is the engine boundary for brief 2.A. Note what it will not do: an
    `Arrest` cannot be produced from an empty or unprovable file, however long the
    rumour travelled or however seriously it was reported.
    """
    if rng >= enforcement_probability(action_tag, corruption):
        return None

    charge = next(
        (c for c in criminal_file.charges if c.action_tag is action_tag and c.provable),
        None,
    )
    if charge is None:
        return Stop(
            reason=f"{action_tag.value} reported, but no provable charge on the file"
        )
    return Arrest(
        file=criminal_file,
        charge=charge,
        officer_entity_id=officer_entity_id,
        district_id=district.district_id,
    )


@dataclass(frozen=True)
class PleaOffer:
    """What the public defender puts on the table.

    Generated from the file, not freehand, so the LLM's dialogue is grounded in
    real numbers rather than improvising consequences.
    """

    offered_charge: Charge
    dropped_charges: list[Charge]
    days_if_accepted: float
    days_if_tried: float
    note: str


def plea_offer(criminal_file: CriminalFile) -> PleaOffer | None:
    """Offer the most serious charge and drop the rest. None if nothing provable.

    Plea value scales with how bad trying it would be, so a single charge is not
    worth taking and a stacked file is.
    """
    provable = criminal_file.provable_charges()
    if not provable:
        return None

    principal = max(provable, key=lambda c: c.severity * c.strength)
    dropped = [c for c in provable if c is not principal]
    trial_total = criminal_file.sentence_if_convicted()

    # Taking the deal concedes the principal charge at reduced weight. The saving
    # scales with the size of what is being dropped, so a thin file sees little
    # reason to plead.
    concession = 0.55 + 0.15 * min(1.0, len(dropped))
    accepted = principal.sentence() * concession
    saving = max(0.0, trial_total - principal.sentence() - accepted)

    return PleaOffer(
        offered_charge=principal,
        dropped_charges=dropped,
        days_if_accepted=round(accepted),
        days_if_tried=round(trial_total),
        note=(
            f"Concede {principal.action_tag.value}, drop "
            f"{len(dropped)} other charge(s), {round(saving)} days saved."
        ),
    )