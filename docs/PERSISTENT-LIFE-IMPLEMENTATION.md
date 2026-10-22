# Persistent Life & Legacy — Implementation Status

This subsystem is being connected to the existing simulation, rather than treated as an isolated design document.

## Python reference systems

- Health conditions persist severity, duration, activity limitations, and gradual recovery.
- Daily life now models treatment costs/effectiveness, bounded uncertain recovery estimates, work capacity, missed wages, stress, and care hours.
- NPC support transfers money, reduces recipient stress, records care providers, and improves directed reciprocal trust.
- Obligations can be settled or missed with money/stress/trust consequences. After death, outstanding debt is considered against the estate, then possible supporters are evaluated using relationships and personality traits; unresolved amounts remain explicit.
- Ghost influence is restricted to authored time windows and allowed action types. The receiving NPC's spiritual openness, fearfulness, stubbornness, memories, and relationships determine receptivity; decisions are logged.
- Campaign life states enforce active -> spectator -> ghost transitions. Death snapshots preserve a world, and starting another life creates a separate day-zero world with read-only archived timelines.
- JSON save/load is versioned for the base world and campaign archives.

## C++ world integration

- `LifeCoordinator` is now part of the portable C++ core and is exposed through `SimulationWorld::life_system()`.
- The world coordinator invokes lifecycle processing on scheduler daily ticks. Medical recovery/treatment costs are applied, and health-adjusted work hours feed the existing wage/missed-work system rather than paying wages twice.
- C++ interfaces cover life state, conditions/treatments, recovery ranges, obligations, death/ghost transitions, time-windowed ghost decisions based on NPC memories and relationships, and support resolution after death. Ghost windows restrict action types to authored `sign`, `sound`, and `dream` actions; each manifestation has a distinct persisted memory/event tag and creates a resolved, witnessed social event. `sound` can raise stress, `dream` can ease isolation/social need, and `sign` can strengthen the NPC's relationship with the ghost. When NPCs talk, they can pass these memories onward; a listener interprets a newly heard manifestation with a bounded social response, while the saved memory prevents that response from being repeatedly applied on later tellings. `CampaignCoordinator` exposes the player-facing influence call and draws its decision sample from the world's saved random stream.
- CMake includes the new source. C++ regression coverage checks recovery ranges, life/ghost transitions, and window gating; Python tests cover treatment/work effects, support/trust, estate handling, and personality-aware ghost influence.

## C++ campaign and archive integration

- `CampaignCoordinator` owns the active `SimulationWorld`, tracks the current life, records death, and allows the dead world to continue running while NPCs settle obligations.
- Starting another life snapshots the old world as an immutable archive, marks the prior character `Archived`, and creates a separate day-zero world. Archive inspection returns a detached world copy, so inspection cannot mutate the preserved snapshot.
- Versioned campaign save/load stores the active world and archive snapshots together. World format v10 persists NPC beliefs, personality biases, and moral value priorities while remaining able to read legacy v5-v9 snapshots.
- Recovery sampling uses stable FNV-1a condition IDs rather than implementation-defined `std::hash`, avoiding compiler-library-dependent outcomes.

## Determinism regression coverage

The C++ regression compares continuous simulation with save/resume at hour 8.5 and at multiple checkpoints across three additional days. Ghost actions are validated against each window's permitted action list; accepted influence updates a manifestation-specific memory, creates a persisted event linked to its witness, and applies action-specific social effects. The replay regression also checks that ghost stories propagate through NPC conversations and a newly informed listener reacts only once to the same manifestation. The campaign API consumes the saved world random stream so decisions, event counts, memory changes, emotional effects, obligations, and serialized bytes match after each checkpoint. Ghost manifestation memories use absolute world hours (not just the time of day), so their decay remains correct on later days. Coverage also checks out-of-window actions, estate/supporter debt settlement, NPC balances, life status, archive immutability, and a new life in a fresh day-zero world. The C++ core remains engine-independent; Unreal UI/animation/game-thread code is not yet wired to this API.

CI for this branch is the verification authority; report only the checks that have actually completed successfully.

## Belief formation and conflicting accounts

- NPCs retain beliefs separately from raw memories, recording the target, event/action, event time, confidence, source, direct-observation status, corroborations, and contradictions.
- First-hand witnesses form high-confidence beliefs. Second-hand accounts are weighted by the listener's relationship with the speaker, the speaker's own balance of direct observation versus hearsay, and the reliability of the retold memory.
- Accounts about the same target and event time can coexist when they disagree. Conflicting reports reduce confidence in competing interpretations instead of silently overwriting the original account; repeated compatible reports increase corroboration and confidence.
- Contradictions create a small stress response and can erode trust in a hostile source. Existing conversation effects also change relationships, social needs, isolation, and stress. Beliefs are saved in world format v9; readers continue to accept v5/v6/v7/v8 snapshots.

## Persistent NPC interpretation biases

- NPCs have stable normalized loyalty, skepticism, and compassion traits; `0.5` is neutral, and old saves default to neutral values.
- During conversation, loyalty biases ambiguous reports in line with the listener's existing relationship to the person discussed. Compassion shifts interpretation of prosocial versus harmful actions, while skepticism reduces confidence in second-hand reports. Neutral trait values preserve the prior confidence calculation.
- Bias changes the listener's interpretation of a rumour, not the recorded event or a directly witnessed account. Competing beliefs remain separate, and the calculation consumes no random samples.
- World format v10 persists these traits and validates their `[0, 1]` range; legacy v5-v8 saves load with neutral defaults.

## Moral choice evaluation

- NPCs persist separate fairness, safety, freedom, and self-interest priorities alongside compassion and loyalty.
- `evaluate_moral_choice` scores scenario options using urgency, people helped, fairness, safety, freedom, loyalty, and personal cost. Scenario features and values are bounded to `[0, 1]`; out-of-range inputs are clamped for evaluation.
- The evaluator is deterministic and side-effect-free. It does not mark an option objectively good or bad, mutate the world, or consume randomness; it returns a comparable score for each option so callers can present trade-offs or select a preferred option. `choose_moral_option` selects the highest score, breaks ties by stable input order, and rejects empty option lists.
- `resolve_moral_choice` now connects selection to authored consequences: the chosen option can change the deciding NPC’s money, stress, and directed relationships. Effects are supplied by the scenario rather than inferred from the score; money cannot fall below zero, stress and relationships are bounded, and invalid or ambiguous option/effect IDs are rejected before mutation. The result reports the choice and actual applied deltas. The mutated NPC state uses existing world persistence; a separate durable decision-history log and full scenario/outcome authoring system remain future work.
- `SimulationWorld::resolve_moral_choice` records each resolved choice in append-only world history: scenario and decision IDs, simulation timestamp, selected option and score, a snapshot of the deciding NPC’s relevant moral priorities, and the actual applied money/stress/relationship deltas. World save format v11 persists this history; v5-v10 snapshots remain readable and load with an empty decision history.
- World format v10 writes the additional value priorities; legacy v5-v9 snapshots retain neutral defaults for fields they do not contain.

## Personality-driven ghost interpretation

- Ghost manifestations are interpreted through the NPC's existing stress, trauma, desperation, relationship with the deceased, and retained memories. A frightened NPC can become more alarmed; a close contact is more likely to seek further contact; a skeptical or weakly connected NPC can become more suspicious or investigate rather than trust immediately.
- Each witnessed manifestation is retained in the event history. Repeated encounters increase history-weighted emotional and relationship consequences and can create durable goals such as `avoid_ghost`, `investigate_ghost`, or `seek_ghost_contact`. Conversation-based stories use the same deterministic personality/history model and are gated by saved memories to avoid repeating the same one-time response.
- These effects use persisted fields and no additional random draws, so uninterrupted and save/resumed simulations can be compared byte-for-byte.
## Rumour ripple and cooperation

- Conversations can shift a listener's directed relationship toward the person discussed. The change is confidence-weighted and does not declare the account objectively true.
- District reputation is derived from persisted resident beliefs. Confidence, direct observation, corroboration, and contradictions affect each account's weight; ghost manifestations are excluded from reputation scoring.
- Cooperation combines personal trust (65%) with community reputation (35%). NPCs can decline resource support when this score is too low, while a strong personal bond can outweigh a poor public reputation. Accepted support transfers money and improves reciprocal trust.
- Hiring combines reciprocal referrals from current employees (60%) with district reputation (40%). Reputation is a soft preference rather than a hard exclusion: missing or disputed accounts affect ranking without making work categorically unavailable.
- When housing is scarce, unhoused residents are considered in stable descending order of district reputation. Affordability, unit capacity, and reciprocal trust for shared housing still apply; reputation changes consideration order, not eligibility. This models the unfair influence of community opinion without treating rumours as objective truth.
- Automatic rent assistance uses reciprocal personal trust (65%) and the recipient's community reputation (35%). A modest relationship can qualify when local standing is positive, while a strong bond can still overcome poor public standing; reputation alone never triggers aid.
- Beliefs, relationships, housing assignments, and money are saved with the world. Regression coverage checks reputation-sensitive hiring and housing, refusal of support, and byte-identical save/resume outcomes.


## Persistent social consequences of direct aid

- Successful aid uses a dedicated `SocialAid` memory/belief tag, distinct from generic politeness. When the story is retold, listeners can form a positive account of the donor, improve their relationship toward them, and contribute to the donor’s local reputation.
- Conflicting accounts about the same target and event hour coexist: a contradictory allegation lowers the aid account's confidence and records contradictions on both beliefs instead of replacing the earlier story. The combined evidence can reverse the donor's local standing, and that disputed state survives save/resume.
- A successful support transfer records a timestamped, attributable interaction memory for both the donor and recipient. The existing memory persistence and conversation-transfer systems carry that history through save/resume and ordinary gossip.
- Aid builds reciprocal relationship trust over repeated encounters, rather than applying only a one-time financial effect.
- Receiving aid also modestly reduces the recipient's stress and desperation, while money balances remain governed by the existing transfer and daily-life systems.
- Regression coverage verifies both sides remember the other, event timestamps match simulation time, recipient state changes, and the result remains equivalent after save/resume.

## Long-term belief confidence

- NPC beliefs gradually lose confidence on daily world ticks rather than remaining frozen forever. Direct observation and corroboration slow the decay; unresolved contradictions accelerate it.
- Decay is bounded and deterministic, consumes no random samples, and uses fields already persisted in world format v8. No save-format change is required.
- Regression coverage compares direct observation, corroborated hearsay, ordinary hearsay, and disputed accounts, and verifies byte-identical save/resume replay across multiple days.


## First-hand evidence revises conflicting beliefs

- When an NPC directly witnesses an action, a different belief about the same target and event hour is retained as a competing account, but its confidence is reduced and its contradiction count increases.
- The directly observed account is recorded at full confidence; the system does not silently delete the earlier interpretation or treat unrelated events at other times as contradictions.
- Regression coverage verifies both beliefs remain distinct and that the challenged confidence, contradiction count, and serialized world survive save/load byte-for-byte.


## Repeated accounts are not independent corroboration

- Repeating the same account from the same speaker does not increase an NPC belief's confidence or corroboration count, and does not repeatedly weaken competing accounts.
- A distinct source can still reinforce second-hand information. Directly observed beliefs retain their first-hand provenance when a matching story is heard.
- Regression coverage checks repeat-telling stability and byte-identical state across equivalent replay.
