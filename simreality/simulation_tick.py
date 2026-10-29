"""Deterministic tick orchestration for explicit world events and NPC conversations.

This is a small, engine-independent scheduling boundary, not an autonomous
world simulator. Callers still decide which events occur, who witnesses them,
and which NPCs converse. The coordinator imposes a stable order and replay rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .model import NPC, NPCMemory
from .routine_execution import RoutineExecutionLedger, RoutineExecution
from .routine_tick import RoutineTickAdapter
from .routines import RoutineBook, RoutineDisruption
from .social_conversations import ConversationBeliefResult, SocialConversationAdapter
from .world_event_memory import WorldEventMemoryAdapter
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class ConversationIntent:
    """One explicitly scheduled conversation for a simulation tick."""

    conversation_id: str
    listener_id: str
    speaker_id: str
    district_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("conversation_id", "listener_id", "speaker_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.listener_id == self.speaker_id:
            raise ValueError("listener and speaker must be different NPCs")
        if self.district_id is not None and (
            not isinstance(self.district_id, str) or not self.district_id.strip()
        ):
            raise ValueError("district_id must be None or a non-empty string")


@dataclass(frozen=True)
class SimulationTickResult:
    """Immutable output from processing one tick."""

    tick: int
    materialized_memories: tuple[tuple[str, str, NPCMemory | None], ...]
    conversations: tuple[ConversationBeliefResult, ...]


class SimulationTickCoordinator:
    """Run caller-supplied event memory and conversation work in stable order.

    Processing order:
      1. materialize memories for explicitly listed witnesses of selected events;
      2. execute explicitly scheduled conversations in conversation-ID order.

    Event memory creation therefore precedes conversations at the same tick.
    This does not invent proximity, visibility, schedules, motives, or outcomes.
    Identical tick replay with identical request inputs returns the original
    result without applying work twice. Conflicting same-tick requests are rejected;
    new ticks must be strictly increasing.
    """

    def __init__(
        self,
        events: WorldEventLedger,
        memory_adapter: WorldEventMemoryAdapter,
        conversation_adapter: SocialConversationAdapter,
    ) -> None:
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(memory_adapter, WorldEventMemoryAdapter):
            raise TypeError("memory_adapter must be a WorldEventMemoryAdapter")
        if memory_adapter.events is not events:
            raise ValueError("memory_adapter must use the same event ledger")
        if not isinstance(conversation_adapter, SocialConversationAdapter):
            raise TypeError("conversation_adapter must be a SocialConversationAdapter")
        self.events = events
        self.memory_adapter = memory_adapter
        self.conversation_adapter = conversation_adapter
        self._requests: dict[int, tuple[object, ...]] = {}
        self._results: dict[int, SimulationTickResult] = {}
        self._last_tick: int | None = None

    @staticmethod
    def _signature(
        event_ids: tuple[str, ...], conversations: tuple[ConversationIntent, ...]
    ) -> tuple[object, ...]:
        return (event_ids, conversations)

    def step(
        self,
        tick: int,
        npcs: Mapping[str, NPC],
        *,
        event_ids: tuple[str, ...] = (),
        conversations: tuple[ConversationIntent, ...] = (),
    ) -> SimulationTickResult:
        """Process a tick using explicit event IDs and conversation intents."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(npcs, Mapping):
            raise TypeError("npcs must be a mapping of NPC IDs to NPC instances")
        for npc_id, npc in npcs.items():
            if not isinstance(npc_id, str) or not npc_id.strip():
                raise ValueError("NPC mapping keys must be non-empty strings")
            if not isinstance(npc, NPC):
                raise TypeError("NPC mapping values must be NPC instances")
            if npc.entity_id != npc_id:
                raise ValueError("NPC mapping keys must match each NPC entity_id")
        if not isinstance(event_ids, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in event_ids
        ):
            raise ValueError("event_ids must be a tuple of non-empty strings")
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event_ids must not contain duplicates")
        if not isinstance(conversations, tuple) or any(
            not isinstance(item, ConversationIntent) for item in conversations
        ):
            raise ValueError("conversations must be a tuple of ConversationIntent values")
        conversation_ids = [item.conversation_id for item in conversations]
        if len(conversation_ids) != len(set(conversation_ids)):
            raise ValueError("conversation IDs must be unique within a tick")

        ordered_events = tuple(sorted(
            (self.events.get(event_id) for event_id in event_ids),
            key=lambda event: (event.tick, event.event_id),
        ))
        for event in ordered_events:
            if event.tick != tick:
                raise ValueError(
                    f"event {event.event_id!r} is at tick {event.tick}, not requested tick {tick}"
                )
            for witness_id in event.witnesses:
                if witness_id not in npcs:
                    raise KeyError(f"witness NPC not supplied: {witness_id}")
        for intent in conversations:
            if intent.listener_id not in npcs:
                raise KeyError(f"listener NPC not supplied: {intent.listener_id}")
            if intent.speaker_id not in npcs:
                raise KeyError(f"speaker NPC not supplied: {intent.speaker_id}")

        ordered_event_ids = tuple(event.event_id for event in ordered_events)
        ordered_conversations = tuple(sorted(conversations, key=lambda item: item.conversation_id))
        signature = self._signature(ordered_event_ids, ordered_conversations)
        if tick in self._requests:
            if self._requests[tick] != signature:
                raise ValueError(f"tick {tick} replayed with different request inputs")
            return self._results[tick]
        if self._last_tick is not None and tick <= self._last_tick:
            raise ValueError("new ticks must be strictly greater than the last processed tick")

        memories: list[tuple[str, str, NPCMemory | None]] = []
        for event in ordered_events:
            for witness_id in sorted(event.witnesses):
                memory = self.memory_adapter.materialize(event.event_id, witness_id, npcs)
                memories.append((event.event_id, witness_id, memory))

        conversation_results = tuple(
            self.conversation_adapter.converse(
                intent.conversation_id,
                listener=npcs[intent.listener_id],
                speaker=npcs[intent.speaker_id],
                observed_tick=tick,
                district_id=intent.district_id,
            )
            for intent in ordered_conversations
        )
        result = SimulationTickResult(tick, tuple(memories), conversation_results)
        self._requests[tick] = signature
        self._results[tick] = result
        self._last_tick = tick
        return result

    def execute_routines(
        self,
        tick: int,
        minute_of_day: int,
        book: RoutineBook,
        ledger: RoutineExecutionLedger,
        *,
        disruptions: Iterable[RoutineDisruption] = (),
        outcome_samples: Mapping[str, float],
        owner_ids: Iterable[str] | None = None,
    ) -> tuple[RoutineExecution, ...]:
        """Resolve scheduled NPC activities as a named phase of a world tick.

        This phase must be called for a tick that has already been processed by
        step(). It uses the same world tick number in execution IDs, so its
        results are replay-safe through the supplied RoutineExecutionLedger and
        can be persisted in the world checkpoint. Inputs and samples remain
        explicit; the coordinator never creates disruptions or randomness.
        """
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if tick not in self._results:
            raise ValueError("routine execution requires a completed world tick")
        if tick != self._last_tick:
            raise ValueError("routine execution must run on the latest completed world tick")
        if not isinstance(book, RoutineBook):
            raise TypeError("book must be a RoutineBook")
        if not isinstance(ledger, RoutineExecutionLedger):
            raise TypeError("ledger must be a RoutineExecutionLedger")
        adapter = RoutineTickAdapter(ledger)
        return adapter.execute_due(
            str(tick), book, minute_of_day,
            disruptions=disruptions,
            outcome_samples=outcome_samples,
            owner_ids=owner_ids,
        )

    def snapshot(self) -> tuple[SimulationTickResult, ...]:
        """Return completed ticks in chronological order."""
        return tuple(self._results[tick] for tick in sorted(self._results))
