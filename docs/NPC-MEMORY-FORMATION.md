# NPC autobiographical memory formation

`NPCAutobiographicalMemoryAdapter` converts immutable world events into observer-owned personal memories. It does not infer emotional meaning or invent a narrative. Each NPC receives an authored `AutobiographicalMemoryProfile` whose rules explicitly match an event type and the observer's role (participant or witness), and supply the interpretation, emotional impact, identity impact, tags, and turning-point designation.

## Processing

Call `NPCAutobiographicalMemoryAdapter.process(events, profiles_by_npc, history)`. Only NPCs listed as participants or witnesses are eligible. A participant uses participant rules; otherwise a witness uses witness rules. Rule order and event order are canonical. Stable memory IDs are derived from event, observer, and rule, making identical replay idempotent. Reusing that identity after changing its authored interpretation or impact is rejected rather than silently rewriting the past.

Rules choose whether other participants and/or witnesses are included in the memory's involved-NPC list. Optional conflict and psychological-learning decision IDs can be supplied in mappings keyed by `(event_id, owner_id)`; these links are copied into the memory as explicit provenance, not inferred.

## Boundaries

This adapter forms memory records only. It does not change objective world events, automatically choose an NPC's rules, infer trauma, or make the NPC recall or discuss a memory. Retrieval remains a separate decision: use `NPCLifeHistory.recall_salience` as one signal, combined with explicit context and authored retrieval policy. The history can be passed to `SimulationWorldCheckpoint.capture(..., life_history=history)` for persistence and source-event validation.
