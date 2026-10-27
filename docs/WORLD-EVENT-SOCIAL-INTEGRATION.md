# World Event → NPC Social Consequences

## Purpose

`WorldEventSocialAdapter` connects the shared event journal to the existing
observer-specific trust and belief systems. It does not change the authoritative
event or invent an interpretation.

## Flow

1. Record a `WorldEvent` with the simulation tick, participants and witnesses.
2. For each witness whose reaction should be simulated, call
   `record_interpretation` with that witness's trust direction/strength and claims.
3. The adapter validates that the observer is a recorded witness and the actor is
   a participant, then delegates to `SocialConsequenceRecorder`.
4. Each witness receives a separate event ID and independent trust/belief updates.

Two witnesses can disagree about the same event. The shared journal says what
occurred; an interpretation says what a particular NPC took from it.

## Scope boundary

The adapter does not detect witnesses, decide whether an action was justified, or
infer trust changes from raw event types. Those choices remain explicit inputs to
keep the system deterministic, inspectable and free of universal morality labels.
