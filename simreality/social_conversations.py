"""Replay-safe orchestration of actual NPC conversations and social beliefs.

This bridge uses the existing gossip conversation function for memory transfer,
then lets the listener evaluate each received rumour using their own trust in the
speaker. It never reads world events or asserts that a rumour is objectively true.
"""
from __future__ import annotations

from dataclasses import dataclass

from .gossip import Conversation, Rumour, converse
from .model import NPC
from .social_beliefs import SocialBeliefSystem
from .social_trust import SocialTrustLedger


@dataclass(frozen=True)
class ConversationBeliefResult:
    conversation_id: str
    conversation: Conversation
    belief_states: tuple[tuple[str, float], ...]


class SocialConversationAdapter:
    """Run a real memory transfer once and record the listener's resulting beliefs.

    The caller supplies a stable conversation ID and simulation tick. Replaying an
    identical request returns the original result without transferring memories or
    applying evidence twice. Reusing an ID with different participants, tick,
    district, or speaker-memory content is rejected.
    """

    def __init__(self, trust: SocialTrustLedger, beliefs: SocialBeliefSystem) -> None:
        if not isinstance(trust, SocialTrustLedger):
            raise TypeError("trust must be a SocialTrustLedger")
        if not isinstance(beliefs, SocialBeliefSystem):
            raise TypeError("beliefs must be a SocialBeliefSystem")
        if beliefs.trust is not trust:
            raise ValueError("beliefs must use the same trust ledger")
        self.trust = trust
        self.beliefs = beliefs
        self._inputs: dict[str, tuple[object, ...]] = {}
        self._results: dict[str, ConversationBeliefResult] = {}

    @staticmethod
    def _memory_signature(npc: NPC) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                m.witness_id, m.target_entity_id, m.initial_impact, m.retention,
                m.timestamp_hour, m.action_tag.value, m.description.height_m,
                m.description.height_uncertainty_m,
                tuple(sorted(m.description.jacket_colour_weights.items())),
                m.description.masked, m.description.masked_confidence,
                m.description.observations,
            )
            for m in npc.memories
        )

    def converse(
        self,
        conversation_id: str,
        listener: NPC,
        speaker: NPC,
        observed_tick: int,
        district_id: str | None = None,
    ) -> ConversationBeliefResult:
        if not isinstance(conversation_id, str) or not conversation_id.strip():
            raise ValueError("conversation_id must be a non-empty string")
        if not isinstance(listener, NPC) or not isinstance(speaker, NPC):
            raise TypeError("listener and speaker must be NPC instances")
        if listener.entity_id == speaker.entity_id:
            raise ValueError("listener and speaker must be different NPCs")
        if isinstance(observed_tick, bool) or not isinstance(observed_tick, int) or observed_tick < 0:
            raise ValueError("observed_tick must be a non-negative integer")
        if district_id is not None and (not isinstance(district_id, str) or not district_id.strip()):
            raise ValueError("district_id must be None or a non-empty string")

        signature = (
            listener.entity_id, speaker.entity_id, observed_tick, district_id,
            self._memory_signature(speaker),
        )
        if conversation_id in self._inputs:
            if self._inputs[conversation_id] != signature:
                raise ValueError(f"conversation ID reused with different input: {conversation_id}")
            return self._results[conversation_id]

        transfer = converse(listener, speaker, district_id)
        states: list[tuple[str, float]] = []
        for index, rumour in enumerate(transfer.transferred):
            if rumour.target_entity_id is None:
                claim_id = f"rumour:{rumour.action_tag}:unattributed"
            else:
                claim_id = f"rumour:{rumour.action_tag}:target:{rumour.target_entity_id}"
            evidence_id = f"conversation:{conversation_id}:rumour:{index}"
            state = self.beliefs.observe_rumour(
                observer_id=listener.entity_id,
                source_id=speaker.entity_id,
                rumour=rumour,
                evidence_id=evidence_id,
                claim_id=claim_id,
                observed_tick=observed_tick,
            )
            states.append((claim_id, state.confidence))

        result = ConversationBeliefResult(
            conversation_id=conversation_id,
            conversation=transfer,
            belief_states=tuple(states),
        )
        self._inputs[conversation_id] = signature
        self._results[conversation_id] = result
        return result

    def snapshot(self) -> tuple[ConversationBeliefResult, ...]:
        """Return recorded conversation results in stable ID order."""
        return tuple(self._results[key] for key in sorted(self._results))
