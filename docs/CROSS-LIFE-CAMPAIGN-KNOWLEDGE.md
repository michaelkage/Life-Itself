# Cross-life campaign knowledge

`CampaignKnowledgeLedger` stores attributed `Evidence` at campaign scope. It is intentionally distinct from a life's `PersonProfile` and from observer-specific `SocialBeliefSystem` ledgers.

## Ownership rules

- Personality, autobiographical memories, and personal relationship values remain owned by the character's LifeSimulation and are preserved in that life’s archive.
- Shared campaign evidence is available after a new life begins, but it is not copied into the new character's memories or relationships.
- Each evidence item retains its evidence ID, claim ID, source ID, support/contradiction direction, strength, source reliability, and observed tick.
- A belief is a deterministic assessment derived from those records. It is not a declaration that a claim is objectively true.
- Reusing an evidence ID with different content is rejected; identical replay is idempotent.

## API

Use `LifeItselfCampaign.record_shared_evidence(evidence)` to add a source-attributed record. Query `shared_evidence_for(claim_id)` to inspect provenance and `shared_belief(claim_id)` to obtain the aggregate confidence and supporting evidence IDs.

The campaign JSON includes `shared_knowledge` only when non-empty. Older campaign JSON without that field loads with an empty ledger. No policy automatically transfers one life’s private memories or personal relationship state to another.

## Explicit NPC knowledge acquisition

A campaign ledger does not automatically populate NPC beliefs. When an NPC actually learns a claim, call `SocialBeliefSystem.learn_campaign_evidence(observer_id, campaign.shared_knowledge, claim_id)`. This imports only that claim's evidence into that observer's private belief ledger. The NPC's current trust in each original source is sampled at learning time, while evidence source IDs, direction, strength, and observation ticks remain attributable. Each imported ID is namespaced as `campaign:<evidence_id>`, preventing collisions with independently acquired reports.

Learning is explicit and observer-scoped: NPCs that have not received the information remain unaware. The resulting belief ledger is covered by the existing `SocialBeliefSnapshot` persistence codec and world checkpoint pipeline.
