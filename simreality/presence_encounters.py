"""Presence-gated social encounters between NPCs at shared symbolic locations.

Co-location creates a possible encounter, never an automatic conversation.
The caller must explicitly confirm an interaction opportunity; optional dialogue
and trust effects are separately requested and replay-safe.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable

from .presence import PresenceLedger
from .social_conversations import SocialConversationAdapter, ConversationBeliefResult
from .social_trust import SocialInteraction, SocialTrustLedger
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class PresenceEncounter:
    encounter_id: str
    tick: int
    location_id: str
    participants: tuple[str, str]
    conversation_id: str | None = None
    trust_interaction_ids: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("encounter_id", "location_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not isinstance(self.participants, tuple) or len(self.participants) != 2:
            raise ValueError("participants must contain exactly two NPC IDs")
        if any(not isinstance(x, str) or not x.strip() for x in self.participants):
            raise ValueError("participant IDs must be non-empty strings")
        if self.participants[0] == self.participants[1]:
            raise ValueError("an NPC cannot encounter themselves")
        if self.participants != tuple(sorted(self.participants)):
            raise ValueError("encounter participants must be sorted canonically")
        if self.conversation_id is not None and (not isinstance(self.conversation_id, str) or not self.conversation_id.strip()):
            raise ValueError("conversation_id must be None or non-empty")
        if (not isinstance(self.trust_interaction_ids, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in self.trust_interaction_ids)
                or tuple(sorted(set(self.trust_interaction_ids))) != self.trust_interaction_ids):
            raise ValueError("trust interaction IDs must be unique, non-empty, and sorted")
        if self.trust_interaction_ids and len(self.trust_interaction_ids) != 2:
            raise ValueError("a bilateral encounter must record both trust directions")


@dataclass(frozen=True)
class PresenceEncounterResult:
    encounter: PresenceEncounter
    conversation: ConversationBeliefResult | None


class PresenceEncounterLedger:
    """Records only caller-confirmed opportunities between co-located NPCs."""

    def __init__(self, records: Iterable[PresenceEncounter] = ()):
        self._records: dict[str, PresenceEncounter] = {}
        self._ticks: dict[int, dict[str, tuple[str, PresenceEncounter]]] = {}
        for record in records:
            if not isinstance(record, PresenceEncounter):
                raise TypeError("records must contain PresenceEncounter values")
            if record.encounter_id in self._records:
                raise ValueError(f"duplicate encounter ID: {record.encounter_id}")
            self._records[record.encounter_id] = record

    def get(self, encounter_id: str) -> PresenceEncounter | None:
        return self._records.get(encounter_id)

    def snapshot(self) -> tuple[PresenceEncounter, ...]:
        return tuple(sorted(self._records.values(), key=lambda x: (x.tick, x.encounter_id)))

    def encounters_for(self, owner_id: str) -> tuple[PresenceEncounter, ...]:
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("owner_id must be a non-empty string")
        return tuple(record for record in self.snapshot() if owner_id in record.participants)

    def between(self, first_id: str, second_id: str) -> tuple[PresenceEncounter, ...]:
        for name, value in (("first_id", first_id), ("second_id", second_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if first_id == second_id:
            raise ValueError("encounter partners must be different NPCs")
        pair = {first_id, second_id}
        return tuple(record for record in self.snapshot() if set(record.participants) == pair)

    def count_between(self, first_id: str, second_id: str) -> int:
        return len(self.between(first_id, second_id))

    def tick_snapshot(self):
        return tuple(
            (tick, json.dumps({key: value[0] for key, value in sorted(entries.items())},
                              sort_keys=True, separators=(",", ":")),
             tuple(value[1] for _key, value in sorted(entries.items())))
            for tick, entries in sorted(self._ticks.items())
        )

    def _record(self, tick: int, signature: str, record: PresenceEncounter):
        entries = self._ticks.get(tick)
        if entries is None:
            if self._ticks and tick <= max(self._ticks):
                raise ValueError("new encounter ticks must advance monotonically")
            entries = {}
            self._ticks[tick] = entries
        prior = entries.get(record.encounter_id)
        if prior is not None:
            if prior[0] != signature:
                raise ValueError(f"conflicting encounter replay: {record.encounter_id}")
            return prior[1]
        existing = self._records.get(record.encounter_id)
        if existing is not None and existing != record:
            raise ValueError(f"encounter ID reused with different content: {record.encounter_id}")
        self._records.setdefault(record.encounter_id, record)
        stored = self._records[record.encounter_id]
        entries[record.encounter_id] = (signature, stored)
        return stored

    def _restore_tick(self, tick, signature, records):
        if tick in self._ticks:
            raise ValueError(f"duplicate encounter tick: {tick}")
        signatures = json.loads(signature)
        if not isinstance(signatures, dict) or sorted(signatures) != sorted(x.encounter_id for x in records):
            raise ValueError("encounter tick signature IDs do not match records")
        self._ticks[tick] = {
            record.encounter_id: (signatures[record.encounter_id], record)
            for record in records
        }


class PresenceSocialAdapter:
    """Validate physical co-presence before an optional social interaction.

    The caller supplies the opportunity flag (for example, line of sight,
    available attention, shared language, or a deliberate approach). This module
    does not infer geometry, awareness, attraction, hostility, or conversation.
    """

    def __init__(self, presence: PresenceLedger, ledger: PresenceEncounterLedger | None = None):
        if not isinstance(presence, PresenceLedger):
            raise TypeError("presence must be a PresenceLedger")
        if ledger is not None and not isinstance(ledger, PresenceEncounterLedger):
            raise TypeError("ledger must be a PresenceEncounterLedger or None")
        self.presence = presence
        self.ledger = ledger or PresenceEncounterLedger()

    def encounter(
        self,
        encounter_id: str,
        first_id: str,
        second_id: str,
        tick: int,
        *,
        opportunity: bool,
        location_id: str | None = None,
        events: WorldEventLedger | None = None,
        conversation: bool = False,
        conversation_id: str | None = None,
        listener=None,
        speaker=None,
        conversation_adapter: SocialConversationAdapter | None = None,
        district_id: str | None = None,
        trust: SocialTrustLedger | None = None,
        trust_directions: tuple[int, int] | None = None,
        trust_strength: float = 0.0,
        trust_context: str = "encounter",
    ) -> PresenceEncounterResult | None:
        if not isinstance(opportunity, bool):
            raise ValueError("opportunity must be a boolean")
        if not opportunity:
            return None
        for name, value in (("encounter_id", encounter_id), ("first_id", first_id), ("second_id", second_id)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if first_id == second_id:
            raise ValueError("an NPC cannot encounter themselves")
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if events is not None and not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger or None")
        if not isinstance(conversation, bool):
            raise ValueError("conversation must be a boolean")
        first = self.presence.get(first_id)
        second = self.presence.get(second_id)
        if first is None or second is None or first.status != "at_location" or second.status != "at_location":
            raise ValueError("both NPCs must be physically at a location")
        if first.location_id != second.location_id:
            raise ValueError("NPCs must share a physical location")
        actual_location = first.location_id
        if location_id is not None and location_id != actual_location:
            raise ValueError("requested encounter location does not match physical presence")
        if tick < max(first.updated_tick, second.updated_tick):
            raise ValueError("encounter cannot precede the latest presence update")
        if conversation:
            if not isinstance(conversation_adapter, SocialConversationAdapter):
                raise TypeError("conversation requires a SocialConversationAdapter")
            if listener is None or speaker is None:
                raise ValueError("conversation requires explicit listener and speaker NPCs")
            if {listener.entity_id, speaker.entity_id} != {first_id, second_id}:
                raise ValueError("conversation participants must match encounter participants")
            if not isinstance(conversation_id, str) or not conversation_id.strip():
                raise ValueError("conversation requires a stable conversation_id")
        elif any(x is not None for x in (conversation_adapter, listener, speaker, conversation_id)):
            raise ValueError("conversation inputs require conversation=True")
        if trust_directions is not None:
            if not isinstance(trust, SocialTrustLedger):
                raise TypeError("trust directions require a SocialTrustLedger")
            if not isinstance(trust_directions, tuple) or len(trust_directions) != 2 or any(isinstance(x, bool) or x not in (-1, 1) for x in trust_directions):
                raise ValueError("trust_directions must contain two values of +1 or -1")
            if isinstance(trust_strength, bool) or not isinstance(trust_strength, (int, float)) or not 0 <= trust_strength <= 1:
                raise ValueError("trust_strength must be in [0, 1]")
            if not isinstance(trust_context, str) or not trust_context.strip():
                raise ValueError("trust_context must be a non-empty string")
            if conversation and trust is not conversation_adapter.trust:
                raise ValueError("conversation and encounter trust effects must share one trust ledger")
        elif trust is not None and trust_strength != 0.0:
            raise ValueError("trust effects require explicit trust_directions")

        signature_payload = {
            "encounter_id": encounter_id, "first": first_id, "second": second_id,
            "tick": tick, "location": actual_location, "conversation": conversation,
            "conversation_id": conversation_id,
            "listener": getattr(listener, "entity_id", None),
            "speaker": getattr(speaker, "entity_id", None),
            "trust_directions": trust_directions, "trust_strength": trust_strength,
            "trust_context": trust_context,
        }
        signature = json.dumps(signature_payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        event_id = f"npc_encounter:{encounter_id}"
        if events is not None:
            expected_event = WorldEventLedger.make_event(
                event_id, tick, "npc_encounter",
                participants=tuple(sorted((first_id, second_id))),
                attributes={"location_id": actual_location, "conversation": conversation},
            )
            try:
                existing_event = events.get(event_id)
            except KeyError:
                existing_event = None
            if existing_event is not None and existing_event != expected_event:
                raise ValueError(f"encounter event ID conflicts with world history: {event_id}")
        prior_tick = self.ledger._ticks.get(tick, {}).get(encounter_id)
        if prior_tick is not None:
            if prior_tick[0] != signature:
                raise ValueError(f"conflicting encounter replay: {encounter_id}")
            existing = prior_tick[1]
            result = self._cached_result(existing, listener, speaker, conversation_adapter)
            if events is not None:
                events.append(WorldEventLedger.make_event(
                    f"npc_encounter:{encounter_id}", tick, "npc_encounter",
                    participants=existing.participants,
                    attributes={"location_id": existing.location_id,
                                "conversation": existing.conversation_id is not None},
                ))
            return result

        prior = self.ledger.get(encounter_id)
        if prior is not None:
            raise ValueError(f"encounter ID already belongs to another tick: {encounter_id}")
        if self.ledger._ticks and tick not in self.ledger._ticks and tick <= max(self.ledger._ticks):
            raise ValueError("new encounter ticks must advance monotonically")

        conversation_result = None
        if conversation:
            conversation_result = conversation_adapter.converse(
                conversation_id, listener, speaker, tick, district_id
            )
        trust_ids = ()
        if trust_directions is not None:
            interactions = (
                SocialInteraction(f"{encounter_id}:trust:{first_id}:{second_id}", first_id, second_id,
                                  trust_directions[0], float(trust_strength), tick, trust_context),
                SocialInteraction(f"{encounter_id}:trust:{second_id}:{first_id}", second_id, first_id,
                                  trust_directions[1], float(trust_strength), tick, trust_context),
            )
            trust.add_many(interactions)
            trust_ids = tuple(sorted(item.interaction_id for item in interactions))
        record = PresenceEncounter(encounter_id, tick, actual_location,
                                   tuple(sorted((first_id, second_id))), conversation_id if conversation else None,
                                   trust_ids)
        stored = self.ledger._record(tick, signature, record)
        if events is not None:
            events.append(WorldEventLedger.make_event(
                f"npc_encounter:{encounter_id}", tick, "npc_encounter",
                participants=stored.participants,
                attributes={"location_id": actual_location, "conversation": conversation},
            ))
        return PresenceEncounterResult(stored, conversation_result)

    @staticmethod
    def _cached_result(record, listener, speaker, adapter):
        if record.conversation_id is None:
            return PresenceEncounterResult(record, None)
        if adapter is None or listener is None or speaker is None:
            raise ValueError("replaying a conversational encounter requires its conversation inputs")
        cached = adapter.snapshot()
        result = next((item for item in cached if item.conversation_id == record.conversation_id), None)
        if result is None:
            raise ValueError("conversation replay result is missing")
        return PresenceEncounterResult(record, result)
