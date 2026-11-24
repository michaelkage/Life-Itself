# Remote branch and pull-request consolidation audit

Audit date: 2026-11-24

## Scope and method

The GitHub remote was inventoried through the repository branches and pull-request APIs. The initial inventory contained 28 remote branches (including `main`) and four open PRs (#26–#29). The post-consolidation remote contains 31 branches (including three temporary consolidation branches) and zero open PRs.

A local Git working tree was not present in this execution environment. A direct `git clone` / `git fetch --all --prune` attempt could not reach github.com because DNS/network access was unavailable. Therefore this audit covers all GitHub remote refs and PRs, but cannot certify unpushed local-only branches on a developer workstation.

Stale branches were not blindly merged. Most feature branches were more than 1,800 commits behind the final main line. Their distinct changes were compared with the current implementation and tests; where a later implementation already contained the feature, the old branch was treated as superseded. The three large integrations were rebased onto the newer main line and merged only after fresh checks passed.

## Integrations merged into main

| PR | Source | Integration |
|---|---|---|
| #29 | `milestone-1-21-systems-integration` | Atomic world tick pipeline; dual clocks and transport; spatial/sensory foundation; lane/intersection admission; collision avoidance; route planning; journey renewal; resource-aware deadlock proposals; durable traffic recovery checkpoints |
| #30 | `implementation/production-foundation` (rebased as `consolidation-production-foundation`) | Population execution loop; subsystem LOD/budget policy; checkpoint participants and rollback; action/world-state integration; inventory, household and economic ledgers; React/Vite app foundation and simulation API boundary |
| #32 | `feature/information-provenance-ledger` and `feature/persistent-moral-decision-history` (rebased as `consolidation-information-provenance-v2`) | Append-only information ledger; evidence-root lineage through NPC relays; belief revision history; recipient-local investigation views; explainable moral choices; durable decision history; world save schema v12 |

All three merged PR heads passed their applicable Python and Linux/Windows C++ Actions checks. PR #30's web application build also passed.

## Original remote feature branches and disposition

| Branch | Disposition in main |
|---|---|
| `campaign-archive-determinism` | Superseded by the newer campaign coordinator, immutable archive snapshots, campaign save/resume, and deterministic replay tests included in main |
| `campaign-ghost-action-api` | Superseded by the campaign ghost-influence API and its current world integration |
| `ci/reputation-cooperation-final` | Regression-only branch; current reputation/cooperation behavior and tests are present in main |
| `feat/deterministic-belief-decay` | Deterministic belief-confidence decay is present in the current world tick implementation and regression suite |
| `feat/direct-evidence-revises-beliefs` | Direct witness evidence challenges conflicting beliefs; persisted revision/evidence context is included by PR #32 |
| `feat/npc-beliefs-conflicting-rumours` | Conflicting account handling, corroboration and contradiction accounting are present; PR #32 adds evidence-root lineage and durable revisions |
| `feat/persistent-social-support-memories` | Social-aid memories and their persistent reputation/trust consequences are present in main |
| `feat/personality-driven-ghost-consequences` | Personality, closeness, fearfulness and memory gates for ghost consequences are present in main |
| `feat/reputation-from-social-aid-memories` | Social-aid memories contribute to community reputation in main |
| `feat/social-ripple-reputation-cooperation` | Cooperation and social-ripple reputation behavior and tests are present in main |
| `feature/deterministic-moral-option-selection` | Deterministic moral-option selection is present; PR #32 adds shared factor explanations and decision-time persistence |
| `feature/ghost-event-replay` | Ghost event influence and replay behavior are present in main |
| `feature/ghost-social-interpretation` | Newly learned ghost-story interpretation and its memory gate are present in main |
| `feature/information-provenance-ledger` | Integrated through PR #32, rebased onto current main |
| `feature/moral-choice-consequences` | Authored moral-choice consequences and deterministic evaluation are present; persistent decision context is in PR #32 |
| `feature/npc-bias-mind-system` | NPC personality/bias factors are present in main; revision explanations are persisted by PR #32 |
| `feature/npc-moral-choice-evaluator` | Integrated evaluator behavior is present; shared explanations and saved decisions are in PR #32 |
| `feature/persistent-moral-decision-history` | Integrated through PR #32, rebased onto current main |
| `feature/reputation-aware-community-aid` | Reputation-aware aid with personal-trust interaction is present in main |
| `feature/reputation-aware-hiring` | Reputation-aware hiring behavior is present in main |
| `feature/reputation-aware-housing` | Reputation-aware housing behavior is present in main |
| `fix/absolute-ghost-memory-time` | Absolute simulation-hour memory timestamps are used in main |
| `fix/repeated-rumours-not-corroboration` | Repeated-source reports do not inflate independent corroboration; PR #32 now preserves the original root evidence ID through multi-hop relays |
| `ghost-action-persistence` | Ghost-action memory and persistence are present in main |
| `implementation/production-foundation` | Superseded by the clean current-main integration in merged PR #30 |
| `milestone-1-21-systems-integration` | Fully integrated by merged PR #29; the remote source branch is now behind main |
| `test/conflicting-aid-accounts` | Conflicting social-aid/assault account and persistence regression coverage is present in main |
| `verify/social-ripple-reputation-cooperation` | Regression-only branch; current social-ripple/reputation behavior and tests are present in main |

## Consolidation branches

- `consolidation-production-foundation`: merged via PR #30.
- `consolidation-information-provenance-v2`: merged via PR #32.
- `consolidation-information-provenance`: superseded by the rebased v2 branch; PR #31 closed.

## Pull-request disposition

- PR #29: merged.
- PR #30: merged.
- PR #32: merged.
- PR #26: closed as superseded by PR #32.
- PR #27: closed as superseded by PR #32.
- PR #28: closed as superseded by PR #30.
- PR #31: closed as superseded by PR #32.

No open pull requests remained at the time of this audit.

## Remaining boundary

The remote feature branches have no remaining unique implementation that needs to be merged based on the inspected diffs and current main tests. The old remote branches are stale snapshots and can be deleted after any desired retention period. Local-only branches could not be inspected because no local repository clone was available and outbound GitHub DNS was unavailable to the shell.
