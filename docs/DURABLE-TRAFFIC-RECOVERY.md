# Durable traffic planning and recovery

## Intersection-aware route costs

Route edges may specify `conflict_pressure_cost_per_reservation` in addition to
traversal, lane-congestion, and hazard costs. The field is appended to preserve
existing aggregate initializers. The route cost is:

`traversal + hazard + lane_occupancy * lane_weight + conflicting_reservations * conflict_weight`.

`IntersectionTrafficCoordinator::conflict_pressure` counts active reservations
at the same intersection whose authored conflict-zone sets overlap the
candidate movement. `conflict_pressure_snapshot` captures all configured
movement pressure deterministically. The four-argument
`TrafficRoutePlanner::plan_live` consumes both lane occupancy and intersection
pressure snapshots at the call boundary. This is reservation pressure, not a
prediction of physical queue length; host geometry remains authoritative.

## Resource-aware deadlock proposals

Wait-for relationships can now identify the concrete blocked resource:
lane or intersection, resource ID, and current blocker. The detector groups
cycles and produces deterministic proposals containing:
- the canonical participant set;
- a deterministic participant with supplied replacement reservations;
- the resources and current owners involved in the cycle;
- replacement lane and intersection reservation requests.

A proposal is advisory. It does not acquire grants, release current grants, or
move an entity. The host must validate the proposed alternative, acquire every
replacement grant while preserving current occupancy, execute the guarded route
handoff, and release old resources only after confirmed clearance.

## Durable checkpoint and deterministic replay

`TrafficRecoveryCheckpoint` captures:
- lane capacities, tick/lease clock, active reservations and wait credits;
- intersection movement definitions, conflict zones, active reservations and
  wait credits;
- journey-scoped physical occupancy renewals;
- route-progress observations, stall counters and the configured threshold;
- pending resource-aware wait-for edges and the exact deterministic recovery proposals, including participants, contested resource owners, and replacement reservation requests.

`save_traffic_recovery_checkpoint` and
`load_traffic_recovery_checkpoint` use a versioned, fixed-width little-endian
binary format with bounded collections, finite-number checks, identity
validation, duplicate rejection, capacity checks, and intersection conflict
validation. The snapshots preserve ordering through ordered maps and sorted
vectors. Restoring the checkpoint and resuming at the next strictly increasing
simulation tick produces the same renewal and progress-monitor decisions.

Persist this checkpoint alongside the ordinary world snapshot. The host must
restore authored route graph/geometry and spatial transforms from its own
world/level data; those are intentionally not inferred from traffic occupancy.
Never restore an expired lease as active. Physical occupancy should be reconciled
against authoritative transforms before resuming movement.


## Cross-resource renewal atomicity

JourneyReservationManager renews lane and intersection leases as one logical
transaction. It snapshots both coordinators before advancing either clock. If
either tick advance or either batch resolution fails, both coordinators are
restored, including lease expiries, wait credits, definitions, and clocks, and
the original failure is propagated. This prevents a partially renewed journey
from retaining only one side of an intersection transition.

Checkpoint writing performs the same cross-resource occupancy checks as
loading before emitting the header: every tracked lane and optional intersection
occupancy must have a corresponding unexpired reservation. Pending resource
edges and proposals are validated for resource kinds, unique identities,
canonical participant ordering, owner identity, and replacement-request
ownership. Invalid checkpoints fail before any bytes are written.

Loading also rejects malformed or duplicate resource wait edges and any trailing
bytes after the versioned checkpoint record. A valid checkpoint is therefore one
unambiguous framed record rather than an accepted prefix of a larger or corrupted
stream.

Checkpoint encoding is staged in memory after structural validation and before
writing to the destination stream. This ensures encoding-limit failures (such as
an oversized identifier) leave the destination untouched; only the final stream
write can fail after output begins.

Multiple resource waits between the same pair of entities are retained as
separate resource edges while the deadlock graph collapses them to one directed
entity-to-entity edge. This preserves resource-level recovery evidence without
feeding duplicate graph edges into strongly connected component detection.

A reservation denial is treated as a failed renewal, not a partial success. If
any tracked journey cannot renew its lane token or required intersection token,
both coordinators are restored and the denial is propagated to the caller. This
prevents a lane grant from committing without its intersection admission, or
vice versa.
