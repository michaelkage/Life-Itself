# Simulation HTTP API contract

This document defines the browser-to-runtime transport boundary. It does not claim that a production HTTP server or Unreal adapter is present.

## Base URL

Set `VITE_SIMULATION_API_URL` to the origin/base path of the trusted simulation API. The browser adapter accepts HTTP or HTTPS URLs and appends the versioned routes below.

## Read a snapshot

`GET /v1/world/snapshot`

Returns a JSON `WorldSnapshot` matching `src/types/domain-contracts.ts`. The response must include schema version 1, campaign identity, monotonically increasing revision, capture timestamp, clock, run state, population counts, district summaries and recent event summaries.

The client rejects structurally invalid snapshots. The API must not expose private NPC memories, credentials, account secrets or unredacted personal data in this public summary.

## Submit a command

`POST /v1/world/commands`

Request body is a `SimulationCommand`. The client sends `Idempotency-Key: <commandId>`. The server must persist command IDs in the same transaction as command acceptance and return the original acknowledgement for an identical retry. Reusing an ID with a different payload must return a conflict error.

Successful response:

```json
{
  "commandId": "client-generated-stable-id",
  "accepted": true,
  "acceptedAtRevision": 42
}
```

Acceptance means queued/accepted, not necessarily executed. Execution outcome belongs in later world snapshots and event history.

## Subscribe to world updates

`GET /v1/world/stream`

The endpoint is a Server-Sent Events stream. Each default `message` event contains one complete, validated `WorldSnapshot` JSON object. The server should emit an initial snapshot after connection and then publish committed revisions only. Clients should reconnect using standard EventSource behavior; the server should support event IDs based on monotonically increasing revisions and honor `Last-Event-ID` where practical.

## Error envelope

Non-2xx responses should use:

```json
{
  "error": {
    "code": "COMMAND_CONFLICT",
    "message": "The command ID was already used with a different payload.",
    "retryable": false
  }
}
```

The browser adapter falls back to a stable HTTP status error when the envelope is missing or malformed.

## Operational and security requirements

- Authenticate every request using the application's account session; the transport adapter intentionally does not invent an authentication scheme.
- Authorize campaign membership and command permissions on the server, never from client-supplied IDs alone.
- Enforce payload size limits, rate limits, schema validation and command allow-lists.
- Keep simulation mutations behind the command queue; snapshot and stream endpoints are read-only.
- Publish only committed revisions. Failed commands must not leak partial state.
- Apply per-account and per-campaign isolation in persistence and streaming subscriptions.
- Use TLS in production and never place service-role credentials in browser environment variables.
- Record command ID, account/campaign scope, accepted revision, execution result and trace correlation ID in server-side observability.

## Current implementation boundary

The web application now has a validated HTTP adapter and can display connection state when configured. The repository still needs the API server, authentication/authorization policy, durable command queue, SSE publisher, and engine worker that implement this contract.
