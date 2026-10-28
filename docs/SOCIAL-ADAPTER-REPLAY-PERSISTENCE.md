# Social Adapter Replay Persistence

`SocialConversationReplaySnapshot` and `SocialConsequenceReplaySnapshot` preserve the replay records and exact results for two social adapters. Both use canonical, versioned JSON and reject unsupported schema versions or duplicate IDs.

## Restore order

Restore the authoritative world-event journal, NPC state, social trust history, and observer-specific belief history first. Then create fresh adapters using those restored trust and belief objects, and restore each adapter replay snapshot into its empty adapter.

Conversation snapshots preserve the input signature used to detect a reused conversation ID with changed participants, tick, district, or speaker-memory content. They also preserve the recorded conversation and transferred rumours. An identical replay therefore returns the recorded result instead of transferring memories or applying belief evidence again.

Consequence snapshots preserve each `WitnessedSocialEvent` input and its exact `SocialConsequenceResult`. An identical event replay returns the recorded result instead of applying the trust change again.

## Important boundary

These codecs restore replay indexes and return values; they do not restore trust or beliefs themselves. Those systems must be restored from `SocialTrustSnapshot` and `SocialBeliefSnapshot` before replaying adapter calls. Restore order matters because the saved result contains the state observed when the original event ran.

This still is not a single complete world-save transaction. `SimulationTickCoordinator` replay history and other adapter-owned state need separate coverage, and the whole save must restore all related state consistently. Run the repository test suite before relying on these codecs in a playable build.