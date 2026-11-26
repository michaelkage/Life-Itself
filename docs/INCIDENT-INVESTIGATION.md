# Incident-scoped investigations

An offence is an event, not an action category. Two thefts committed by the same actor are separate incidents even when they have the same action tag.

## Evidence association

`SimulationWorld::build_criminal_file(player_id, incident_id)` resolves the selected `OngoingEvent`, validates that it belongs to the requested actor, and gathers the root evidence identities recorded by that event's original witnesses. It then includes recipient memories carrying those roots, so gossip can deliver evidence to investigators without changing the incident to which the evidence belongs.

The event's creation hour, actor, and action tag are checked alongside root identity. This prevents memories from a different event with the same action tag from entering the file. Legacy memories without root IDs are accepted only from the event's recorded original witnesses.

The existing `build_criminal_file(player_id)` aggregate API remains available for reputation and broad character-history queries. Legal decisions that concern one incident should use the incident-scoped overload. The `resolve_criminal_incident(incident_id, officer_id)` entry point validates that the event is a criminal offence, builds its incident-scoped file, and passes that file through the existing district enforcement rules. This removes the need for a caller to accidentally supply an aggregate file from unrelated events.

## Investigation advancement

Daily investigation progress is based only on actionable memories whose target, action tag, and observation timestamp match the ongoing event. A witness's stale memory of an earlier event cannot advance a later investigation merely because the actor and action category are the same.

## Determinism and persistence

Incident identity is the durable `OngoingEvent.event_id`. Evidence identity remains the root ID already persisted on NPC memories. No new random draws or time-dependent ordering are introduced. Existing world snapshots retain their current schema because this change adds no persisted fields.

## Regression coverage

C++ core tests cover:
- Separate incidents with the same actor and action produce separate criminal files.
- A later single-witness incident does not inherit corroboration from an earlier two-witness incident.
- Unknown incident IDs and actor/incident mismatches are rejected.
- A stale witness memory cannot advance a later event's investigation progress.
