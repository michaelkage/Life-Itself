"""Gossip: how a rumour mutates as it spreads.

No global crime tracker. Information moves only when two NPCs are physically
together and actually talk, and it loses precision on every hop:

    witness sees crime -> tells a friend -> description drifts -> police act on
    the drift, not the truth

The mechanism is one predicate. A witness can only name who they saw while their
retention clears `TELEPHONE_THRESHOLD`; below it, the target's ID is dropped and
only the description propagates. Everything else here is what that looks like in
motion.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Description, NPC, NPCMemory


@dataclass
class Rumour:
    """A description of a crime that has lost its attribution.

    Once `target_entity_id` is None the rumour can no longer convict anyone --
    but police can still act on the appearance, which is the point. A rumour that
    reaches District 4 with a dark-jacket description puts a stop on anyone in a
    dark jacket, guilty or not.
    """

    action_tag: str
    target_entity_id: str | None
    description: Description
    retention: float
    district_id: str | None = None
    #: How many times this has been retold. Provenance, and a police sanity check:
    #: a rumour nobody has corroborated is worth very little.
    corroborations: int = 1

    @property
    def is_attributable(self) -> bool:
        return self.target_entity_id is not None

    def corroborate(self, other: "Rumour") -> "Rumour":
        """Two independent witnesses to the same crime. Sharpen it.

        Two sources agreeing is worth more than either alone -- that is why
        corroboration raises confidence rather than just averaging.
        """
        merged = self.description.merge(other.description, other.retention)
        if self.target_entity_id == other.target_entity_id:
            keep_id = self.target_entity_id
        else:
            keep_id = None  # conflicting IDs -- stop pretending we know who it was

        return Rumour(
            action_tag=self.action_tag,
            target_entity_id=keep_id,
            description=merged,
            retention=max(self.retention, other.retention),
            district_id=self.district_id or other.district_id,
            corroborations=self.corroborations + 1,
        )


@dataclass
class Conversation:
    """One socialising encounter between two NPCs."""

    npc_a: str
    npc_b: str
    district_id: str | None = None
    transferred: list[Rumour] = field(default_factory=list)


#: Below this, a memory is noise and is not repeated at all.
FLOOR_UNATTRIBUTED = 0.01

#: Below this, an *attributed* memory is not repeated. Deliberately much higher
#: than `FLOOR_UNATTRIBUTED`.
#:
#: Naming a person in a crime is an accusation, and an accusation needs real
#: evidence behind it -- this is what keeps the city from filling with unfounded
#: arrests. Passing on "someone tall in a dark jacket" is idle talk that costs the
#: teller nothing, so it survives at a fraction of the retention. Using one cutoff
#: for both silently kills a rumour the moment it stops naming the player, which
#: is exactly backwards from the design: the appearance-only phase is what makes
#: police stop the wrong person.
FLOOR_ATTRIBUTED = 0.05


def retell(memory: NPCMemory) -> Rumour | None:
    """Turn one witness's memory into something passable.

    Returns None if the memory is too faint to transmit at all. A witness who has
    retained almost nothing says "something happened, maybe", which is noise, not
    information -- propagating it would let every rumour fill the city.
    """
    floor = FLOOR_ATTRIBUTED if memory.is_actionable else FLOOR_UNATTRIBUTED
    if memory.retention <= floor:
        return None

    # The whole telephone effect. Above threshold the name survives; below it,
    # the listener gets an appearance and nothing else.
    target_id = memory.target_entity_id if memory.retention >= 0.6 else None

    return Rumour(
        action_tag=memory.action_tag.value,
        target_entity_id=target_id,
        description=memory.description,
        retention=memory.retention,
    )


def converse(listener: NPC, speaker: NPC, district_id: str | None = None) -> Conversation:
    """One NPC tells another everything they remember about a shared subject.

    Only memories whose subject both parties have some stake in get discussed --
    the spec's "intersection check". Listener gains a memory per rumour, with the
    speaker's retention transferred as their own starting impact: hearing something
    weak leaves a weak impression.
    """
    conversation = Conversation(npc_a=speaker.entity_id, npc_b=listener.entity_id,
                                district_id=district_id)

    for memory in speaker.memories:
        # Note what is deliberately NOT here: any check for the speaker having lost
        # the target's name. A memory below threshold is exactly the one that must
        # keep travelling -- it is the rumour that has degraded into "tall person
        # in a dark jacket", and propagating it is the entire point. `retell`
        # already drops memories too faint to be worth repeating.
        rumour = retell(memory)
        if rumour is None:
            continue
        rumour.district_id = district_id

        match_index = None
        if memory.target_entity_id:
            for index, candidate in enumerate(listener.memories):
                if candidate.target_entity_id == memory.target_entity_id:
                    match_index = index

        if match_index is not None:
            # Corroborate the matching event without overwriting an unrelated memory.
            existing = listener.memories_of(memory.target_entity_id)
            prior_memory = listener.memories[match_index]
            prior = Rumour(
                action_tag=prior_memory.action_tag.value,
                target_entity_id=prior_memory.target_entity_id,
                description=prior_memory.description,
                retention=prior_memory.retention,
                district_id=district_id,
                corroborations=len(existing) + 1,
            )
            rumour = prior.corroborate(rumour)
            listener.memories[match_index] = NPCMemory(
                witness_id=listener.entity_id,
                target_entity_id=rumour.target_entity_id,
                initial_impact=max(prior.retention, rumour.retention),
                retention=max(prior.retention, rumour.retention),
                timestamp_hour=memory.timestamp_hour,
                action_tag=memory.action_tag,
                description=rumour.description,
            )
        else:
            listener.remember(
                NPCMemory(
                    witness_id=listener.entity_id,
                    target_entity_id=rumour.target_entity_id,
                    initial_impact=rumour.retention,
                    retention=rumour.retention,
                    timestamp_hour=memory.timestamp_hour,
                    action_tag=memory.action_tag,
                    description=rumour.description,
                )
            )

        conversation.transferred.append(rumour)

    return conversation


def police_response(rumour: Rumour, district_id: str) -> str:
    """What a patrol does about a rumour that reached it.

    The end of the pipeline. An unattributable rumour cannot produce an arrest, so
    it produces a stop instead -- the game punishing the wrong person for a
    faithful copy of the truth.
    """
    if rumour.target_entity_id is not None and rumour.retention >= 0.6:
        return f"District {district_id}: pursue identification for {rumour.target_entity_id}"
    if rumour.description.jacket_confidence > 0.6:
        return f"District {district_id}: stop and search matching {rumour.description.describe()}"
    return f"District {district_id}: logged, insufficient detail to act on ({rumour.description.describe()})"