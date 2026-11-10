# Presence-gated NPC social encounters

`PresenceSocialAdapter` connects authoritative physical presence to the existing
conversation and trust systems. Both NPCs must be recorded as `at_location` at
the same symbolic location. A travelling, blocked, or unreachable NPC cannot
participate as if standing at the current graph node.

Co-location is only a possibility, not an automatic social event. The world
driver must explicitly pass `opportunity=True` after its own rules establish
that the pair could interact. Those rules may eventually include distance,
line of sight, attention, noise, language, social context, or deliberate approach;
this adapter does not fabricate any of those facts.

A confirmed encounter is recorded with a stable ID and can emit an
`npc_encounter` world event. Actual dialogue is opt-in: pass
`conversation=True`, the existing `SocialConversationAdapter`, and explicit
listener/speaker NPC objects. This performs the existing memory transfer and
observer-specific belief update. Merely meeting does not cause gossip.

Trust changes are also opt-in. The caller must provide a trust ledger, a
direction for each participant, and an explicit strength. The adapter does not
decide whether an encounter is friendly, hostile, romantic, awkward, or neutral.
The same encounter may improve one NPC's trust while damaging the other's,
preserving asymmetric interpretations.

`PresenceEncounterSnapshot` stores encounter records and per-tick replay
signatures in canonical JSON. Restore it with the same presence, conversation,
and trust components before replaying later ticks. The world checkpoint can
store this snapshot as an optional `presence_encounters` section.

Regression coverage: `tests/test_presence_encounters.py`.

The encounter ledger also exposes `encounters_for(owner_id)`, `between(a, b)`,
and `count_between(a, b)`. These give later relationship/familiarity systems
an auditable history of repeated contact without forcing a trust change or
assuming that every meeting was friendly. Encounter records are bilateral, but
trust effects remain directional and independently configurable.
