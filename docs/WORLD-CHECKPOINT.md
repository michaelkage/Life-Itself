# World checkpoint

`SimulationWorldCheckpoint` is the composite canonical JSON boundary for the currently integrated Python simulation pipeline. It captures the authoritative event journal, NPC state and memories, trust interactions, observer-specific belief/evidence history, memory-adapter replay keys, conversation replay signatures/results, tick-coordinator replay history, and—when supplied—the separate witnessed-social-consequence recorder's replay inputs/results.

## Capture and restore

Use `SimulationWorldCheckpoint.capture(current_tick, coordinator, npcs, metadata=..., consequence_recorder=...)` to capture a consistent set of components. The optional `consequence_recorder` must share the coordinator's trust ledger and belief system. The resulting JSON is deterministic and sorted; the `consequence_replay` section is emitted only when a recorder was included.

Restore creates the event ledger, NPCs, trust, beliefs, memory adapter and replay index, conversation adapter and replay index, tick coordinator and replay history, then the optional consequence recorder and its replay index. Existing trust and belief histories are restored before consequence replay records, so replaying a previously recorded witnessed event returns its original result rather than applying its trust/evidence effects twice.

## Scope and limitations

This is a persistence boundary for the currently connected Python reference systems, not yet a complete game save format. Capture does not provide a cross-component single-lock atomic snapshot; callers should pause mutation while capturing. The coordinator does not automatically invoke the separate `WorldEventSocialAdapter` or `SocialConsequenceRecorder`; callers still explicitly record witnessed interpretations and pass the recorder to capture. Unreal presentation, engine state, schedules, and all future simulation systems are outside this checkpoint until explicitly integrated. A checkpoint round trip and replay tests exist in `tests/test_world_checkpoint.py`; they must be run in the repository environment before claiming a verified pass.
