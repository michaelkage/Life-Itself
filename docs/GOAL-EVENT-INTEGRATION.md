# Goal progress from world events

**Status:** First engine-independent integration slice.

SRE already models goals separately from daily routines and records routine outcomes in the authoritative world-event journal. This adapter provides a narrow connection between those systems: explicitly configured events can advance explicitly selected goal categories.

## Contract

A GoalProgressPolicy names an event type, goal category, positive progress increment, and optional exact attribute requirements. An event advances a goal only when:
- the NPC is listed as an event participant (witnesses do not count as actors);
- event type and required attributes match exactly;
- the goal belongs to that NPC, has the configured category, and is active.

Progress is capped at 1.0 and uses the existing GoalBook completion rule. Processing order is stable by tick and event ID. Identical event replay is a no-op; conflicting reuse of an event ID is rejected.

## Example

A training_completed event with qualification=mechanic can advance an active career goal by 0.25. A cooking qualification does not match. No event is interpreted without a caller-authored policy.

## Boundaries and next work

This module does not create goals, infer what an event means, generate training events, execute plans, or update goal confidence. Its processed-event index is currently in memory only and is not yet included in SimulationWorldCheckpoint. Persistent replay protection is a required follow-up before using this adapter in a long-running saved campaign.

Regression tests: tests/test_goal_events.py.
