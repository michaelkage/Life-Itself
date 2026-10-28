"""Versioned persistence for social conversation and consequence replay indexes."""
from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any

from .beliefs import BeliefState
from .gossip import Conversation, Rumour
from .model import Description
from .social_conversations import ConversationBeliefResult, SocialConversationAdapter
from .social_consequences import (ObservedClaim, SocialConsequenceRecorder, SocialConsequenceResult, WitnessedSocialEvent)
from .social_trust import SocialTrustState

def _description_dict(d: Description) -> dict[str, Any]:
    return {"height_m": d.height_m, "height_uncertainty_m": d.height_uncertainty_m,
            "jacket_colour_weights": dict(sorted(d.jacket_colour_weights.items())),
            "masked": d.masked, "masked_confidence": d.masked_confidence, "observations": d.observations}

def _description_from(d: dict[str, Any]) -> Description:
    try:
        return Description(d["height_m"], d["height_uncertainty_m"], dict(d["jacket_colour_weights"]),
                           d["masked"], d["masked_confidence"], d["observations"])
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("invalid rumour description") from exc

def _rumour_dict(r: Rumour) -> dict[str, Any]:
    return {"action_tag": r.action_tag, "target_entity_id": r.target_entity_id,
            "description": _description_dict(r.description), "retention": r.retention,
            "district_id": r.district_id, "corroborations": r.corroborations}

def _rumour_from(r: dict[str, Any]) -> Rumour:
    try:
        return Rumour(r["action_tag"], r["target_entity_id"], _description_from(r["description"]),
                      r["retention"], r["district_id"], r["corroborations"])
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("invalid saved rumour") from exc

def _freeze(value: Any) -> Any:
    if isinstance(value, list): return tuple(_freeze(x) for x in value)
    if isinstance(value, dict): return tuple(sorted((k, _freeze(v)) for k, v in value.items()))
    return value

def _trust_dict(s: SocialTrustState) -> dict[str, Any]:
    return {"observer_id": s.observer_id, "target_id": s.target_id, "trust": s.trust,
            "interaction_ids": list(s.interaction_ids), "last_updated_tick": s.last_updated_tick}

def _trust_from(s: dict[str, Any]) -> SocialTrustState:
    return SocialTrustState(s["observer_id"], s["target_id"], s["trust"], tuple(s["interaction_ids"]), s["last_updated_tick"])

def _belief_dict(b: BeliefState) -> dict[str, Any]:
    return {"claim_id": b.claim_id, "confidence": b.confidence, "evidence_ids": list(b.evidence_ids),
            "last_updated_tick": b.last_updated_tick}

def _belief_from(b: dict[str, Any]) -> BeliefState:
    return BeliefState(b["claim_id"], b["confidence"], tuple(b["evidence_ids"]), b["last_updated_tick"])

@dataclass(frozen=True)
class SocialConversationReplaySnapshot:
    """Replay signatures and exact return values; beliefs/trust must be restored separately."""
    entries: tuple[tuple[str, tuple[Any, ...], ConversationBeliefResult], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, adapter: SocialConversationAdapter) -> "SocialConversationReplaySnapshot":
        return cls(tuple((key, adapter._inputs[key], adapter._results[key]) for key in sorted(adapter._results)))

    def restore(self, adapter: SocialConversationAdapter) -> None:
        if not isinstance(adapter, SocialConversationAdapter): raise TypeError("adapter must be SocialConversationAdapter")
        if adapter._inputs or adapter._results: raise ValueError("conversation adapter must be empty before restore")
        for key, signature, result in self.entries:
            if key != result.conversation_id: raise ValueError("conversation replay ID mismatch")
            adapter._inputs[key] = signature
            adapter._results[key] = result

    def to_json(self) -> str:
        entries = []
        for key, sig, result in self.entries:
            conv = result.conversation
            entries.append({"conversation_id": key, "signature": sig,
                "conversation": {"npc_a": conv.npc_a, "npc_b": conv.npc_b, "district_id": conv.district_id,
                                "transferred": [_rumour_dict(r) for r in conv.transferred]},
                "belief_states": [list(x) for x in result.belief_states]})
        return json.dumps({"schema_version": self.SCHEMA_VERSION, "entries": entries}, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "SocialConversationReplaySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION: raise ValueError("unsupported conversation replay schema version")
            entries = []
            for item in raw["entries"]:
                c = item["conversation"]
                conv = Conversation(c["npc_a"], c["npc_b"], c["district_id"], [_rumour_from(r) for r in c["transferred"]])
                result = ConversationBeliefResult(item["conversation_id"], conv, tuple((x[0], x[1]) for x in item["belief_states"]))
                entries.append((item["conversation_id"], _freeze(item["signature"]), result))
            entries.sort(key=lambda x: x[0])
            ids = [x[0] for x in entries]
            if len(ids) != len(set(ids)): raise ValueError("duplicate conversation replay ID")
            return cls(tuple(entries))
        except ValueError: raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc: raise ValueError("invalid conversation replay snapshot") from exc

@dataclass(frozen=True)
class SocialConsequenceReplaySnapshot:
    """Witnessed event inputs and exact return values; side-effect ledgers restore separately."""
    entries: tuple[tuple[WitnessedSocialEvent, SocialConsequenceResult], ...]
    SCHEMA_VERSION = 1

    @classmethod
    def capture(cls, recorder: SocialConsequenceRecorder) -> "SocialConsequenceReplaySnapshot":
        return cls(tuple((recorder._events[key], recorder._results[key]) for key in sorted(recorder._events)))

    def restore(self, recorder: SocialConsequenceRecorder) -> None:
        if not isinstance(recorder, SocialConsequenceRecorder): raise TypeError("recorder must be SocialConsequenceRecorder")
        if recorder._events or recorder._results: raise ValueError("consequence recorder must be empty before restore")
        for event, result in self.entries:
            if event.event_id != result.event_id: raise ValueError("consequence replay ID mismatch")
            recorder._events[event.event_id] = event
            recorder._results[event.event_id] = result

    def to_json(self) -> str:
        entries = []
        for event, result in self.entries:
            entries.append({"event": {"event_id": event.event_id, "observer_id": event.observer_id, "actor_id": event.actor_id,
                "observed_tick": event.observed_tick, "trust_direction": event.trust_direction, "trust_strength": event.trust_strength,
                "claims": [{"claim_id": c.claim_id, "direction": c.direction, "strength": c.strength} for c in event.claims]},
                "result": {"event_id": result.event_id, "trust_state": _trust_dict(result.trust_state),
                           "beliefs": [_belief_dict(b) for b in result.beliefs]}})
        return json.dumps({"schema_version": self.SCHEMA_VERSION, "entries": entries}, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "SocialConsequenceReplaySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION: raise ValueError("unsupported consequence replay schema version")
            entries = []
            for item in raw["entries"]:
                e, r = item["event"], item["result"]
                event = WitnessedSocialEvent(e["event_id"], e["observer_id"], e["actor_id"], e["observed_tick"], e["trust_direction"], e["trust_strength"],
                    tuple(ObservedClaim(c["claim_id"], c["direction"], c["strength"]) for c in e["claims"]))
                result = SocialConsequenceResult(r["event_id"], _trust_from(r["trust_state"]), tuple(_belief_from(b) for b in r["beliefs"]))
                entries.append((event, result))
            entries.sort(key=lambda x: x[0].event_id)
            ids = [x[0].event_id for x in entries]
            if len(ids) != len(set(ids)): raise ValueError("duplicate consequence replay ID")
            return cls(tuple(entries))
        except ValueError: raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc: raise ValueError("invalid consequence replay snapshot") from exc
