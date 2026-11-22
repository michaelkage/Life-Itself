"""Persistence for SimulationTickCoordinator replay history.

Restore event, memory and conversation adapter state before restoring this
coordinator cache. Version 2 stores explicit witness-level memory requests;
version 1 snapshots are migrated from their all-witness event references.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .simulation_tick import (
    ConversationIntent, SimulationTickCoordinator, SimulationTickResult,
)


@dataclass(frozen=True)
class _TickEntry:
    tick: int
    event_ids: tuple[str, ...]
    memory_requests: tuple[tuple[str, str], ...]
    conversations: tuple[ConversationIntent, ...]
    memory_refs: tuple[tuple[str, str, bool], ...]
    conversation_ids: tuple[str, ...]


@dataclass(frozen=True)
class SimulationTickReplaySnapshot:
    """Coordinator replay keys plus references to already-restored adapter outputs."""

    entries: tuple[_TickEntry, ...]
    SCHEMA_VERSION = 2

    @classmethod
    def capture(cls, coordinator: SimulationTickCoordinator) -> "SimulationTickReplaySnapshot":
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        entries = []
        for tick in sorted(coordinator._results):
            result = coordinator._results[tick]
            event_ids, memory_requests, intents = coordinator._requests[tick]
            memory_refs = tuple(
                (event_id, witness_id, memory is None)
                for event_id, witness_id, memory in result.materialized_memories
            )
            if tuple((event_id, witness_id) for event_id, witness_id, _ in memory_refs) != memory_requests:
                raise ValueError("coordinator memory request cache conflicts with its result")
            entries.append(_TickEntry(
                tick=tick,
                event_ids=event_ids,
                memory_requests=memory_requests,
                conversations=intents,
                memory_refs=memory_refs,
                conversation_ids=tuple(item.conversation_id for item in result.conversations),
            ))
        return cls(tuple(entries))

    def to_json(self) -> str:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "entries": [{
                "tick": entry.tick,
                "event_ids": list(entry.event_ids),
                "memory_requests": [list(item) for item in entry.memory_requests],
                "conversations": [{
                    "conversation_id": item.conversation_id,
                    "listener_id": item.listener_id,
                    "speaker_id": item.speaker_id,
                    "district_id": item.district_id,
                } for item in entry.conversations],
                "memory_refs": [list(item) for item in entry.memory_refs],
                "conversation_ids": list(entry.conversation_ids),
            } for entry in self.entries],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "SimulationTickReplaySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") not in (1, cls.SCHEMA_VERSION):
                raise ValueError("unsupported simulation tick replay schema version")
            version = raw["schema_version"]
            entries = []
            for item in raw["entries"]:
                intents = tuple(ConversationIntent(
                    conversation_id=c["conversation_id"],
                    listener_id=c["listener_id"],
                    speaker_id=c["speaker_id"],
                    district_id=c["district_id"],
                ) for c in item["conversations"])
                refs = tuple((ref[0], ref[1], ref[2]) for ref in item["memory_refs"])
                if any(not isinstance(a, str) or not isinstance(b, str) or not isinstance(n, bool)
                       for a, b, n in refs):
                    raise ValueError("invalid memory replay reference")
                if version == 1:
                    memory_requests = tuple((event_id, witness_id) for event_id, witness_id, _ in refs)
                else:
                    memory_requests = tuple((pair[0], pair[1]) for pair in item["memory_requests"])
                entry = _TickEntry(
                    tick=item["tick"],
                    event_ids=tuple(item["event_ids"]),
                    memory_requests=memory_requests,
                    conversations=intents,
                    memory_refs=refs,
                    conversation_ids=tuple(item["conversation_ids"]),
                )
                if isinstance(entry.tick, bool) or not isinstance(entry.tick, int) or entry.tick < 0:
                    raise ValueError("invalid tick in replay snapshot")
                if any(not isinstance(x, str) or not x.strip() for x in entry.event_ids + entry.conversation_ids):
                    raise ValueError("invalid replay ID")
                if len(entry.event_ids) != len(set(entry.event_ids)):
                    raise ValueError("duplicate event ID in tick request")
                if len(entry.conversation_ids) != len(set(entry.conversation_ids)):
                    raise ValueError("duplicate conversation ID in tick result")
                if tuple(sorted(entry.conversations, key=lambda c: c.conversation_id)) != entry.conversations:
                    raise ValueError("conversation intents must be sorted")
                if tuple(sorted(entry.memory_requests)) != entry.memory_requests:
                    raise ValueError("memory requests must be sorted")
                if len(set(entry.memory_requests)) != len(entry.memory_requests):
                    raise ValueError("duplicate memory request")
                if tuple(sorted(entry.memory_refs, key=lambda x: (x[0], x[1]))) != entry.memory_refs:
                    raise ValueError("memory references must be sorted")
                if tuple((a, b) for a, b, _ in entry.memory_refs) != entry.memory_requests:
                    raise ValueError("memory references do not match memory requests")
                entries.append(entry)
            entries.sort(key=lambda e: e.tick)
            ticks = [e.tick for e in entries]
            if len(ticks) != len(set(ticks)):
                raise ValueError("duplicate tick in replay snapshot")
            return cls(tuple(entries))
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid simulation tick replay snapshot") from exc

    def restore(self, coordinator: SimulationTickCoordinator) -> None:
        """Restore cached results after the event/memory/conversation adapters are restored."""
        if not isinstance(coordinator, SimulationTickCoordinator):
            raise TypeError("coordinator must be a SimulationTickCoordinator")
        if coordinator._requests or coordinator._results or coordinator._last_tick is not None:
            raise ValueError("coordinator must be empty before restore")
        restored: list[tuple[int, tuple[object, ...], SimulationTickResult]] = []
        for entry in self.entries:
            ordered_events = tuple(sorted(
                (coordinator.events.get(event_id) for event_id in entry.event_ids),
                key=lambda event: (event.tick, event.event_id),
            ))
            if any(event.tick != entry.tick for event in ordered_events):
                raise ValueError("saved event tick does not match coordinator request")
            if tuple(event.event_id for event in ordered_events) != entry.event_ids:
                raise ValueError("saved event IDs are not in canonical order")
            for event in ordered_events:
                expected = {(event.event_id, witness_id) for witness_id in event.witnesses}
                if not expected.issubset(set(entry.memory_requests)):
                    raise ValueError("saved request omits a same-tick event witness")
            for event_id, witness_id in entry.memory_requests:
                event = coordinator.events.get(event_id)
                if event.tick > entry.tick:
                    raise ValueError("saved memory request references a future event")
                if witness_id not in event.witnesses:
                    raise ValueError("saved memory reference is not a recorded witness")
            actual_memory_keys = tuple((event_id, witness_id) for event_id, witness_id, _ in entry.memory_refs)
            if actual_memory_keys != entry.memory_requests:
                raise ValueError("saved memory references do not match the tick's witness requests")
            if tuple(item.conversation_id for item in entry.conversations) != entry.conversation_ids:
                raise ValueError("saved conversation IDs do not match the tick request")
            memories = []
            for event_id, witness_id, was_none in entry.memory_refs:
                memory = coordinator.memory_adapter._processed.get((event_id, witness_id))
                if was_none:
                    if memory is not None:
                        raise ValueError("saved null memory conflicts with restored memory index")
                elif memory is None:
                    raise ValueError("required materialized memory was not restored")
                memories.append((event_id, witness_id, memory))
            conversations = []
            for conversation_id in entry.conversation_ids:
                result = coordinator.conversation_adapter._results.get(conversation_id)
                if result is None:
                    raise ValueError("required conversation result was not restored")
                intent = entry.conversations[len(conversations)]
                if (
                    result.conversation.npc_a != intent.speaker_id
                    or result.conversation.npc_b != intent.listener_id
                    or result.conversation.district_id != intent.district_id
                ):
                    raise ValueError("restored conversation result conflicts with tick request")
                conversations.append(result)
            signature = (entry.event_ids, entry.memory_requests, entry.conversations)
            result = SimulationTickResult(entry.tick, tuple(memories), tuple(conversations))
            restored.append((entry.tick, signature, result))
        if restored and any(restored[i][0] >= restored[i + 1][0] for i in range(len(restored) - 1)):
            raise ValueError("ticks must be strictly increasing")
        for tick, signature, result in restored:
            coordinator._requests[tick] = signature
            coordinator._results[tick] = result
        coordinator._last_tick = restored[-1][0] if restored else None
