"""Evidence-grounded transfer of NPC experiences without false autobiography.

A recipient receives a reported account, never a personal memory. Both the
original experience and the later communication must exist in the authoritative
world journal. The source autobiographical record remains immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from .npc_life_history import NPCLifeHistory
from .world_events import WorldEventLedger


@dataclass(frozen=True)
class ReportedExperience:
    transfer_id: str
    recipient_id: str
    source_npc_id: str
    source_memory_id: str
    source_event_id: str
    communication_event_id: str
    source_tick: int
    transfer_tick: int
    account: str
    source_role: str
    confidence: float

    def __post_init__(self):
        for name in ("transfer_id", "recipient_id", "source_npc_id", "source_memory_id",
                     "source_event_id", "communication_event_id", "account"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.recipient_id == self.source_npc_id:
            raise ValueError("recipient and source NPC must differ")
        for name in ("source_tick", "transfer_tick"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.source_tick > self.transfer_tick:
            raise ValueError("reported experience cannot precede its source")
        if self.source_role not in ("participant", "witness"):
            raise ValueError("source_role must be participant or witness")
        if (isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float))
                or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError("confidence must be finite and in [0, 1]")


@dataclass(frozen=True)
class ExperienceTransferSnapshot:
    records: tuple[ReportedExperience, ...]

    def __post_init__(self):
        if not isinstance(self.records, tuple) or any(not isinstance(x, ReportedExperience) for x in self.records):
            raise TypeError("records must be a tuple of ReportedExperience")
        ids = [x.transfer_id for x in self.records]
        if ids != sorted(set(ids)):
            raise ValueError("transfer IDs must be unique and sorted")

    def to_json(self):
        return json.dumps({"schema_version": 1, "records": [
            {name: getattr(x, name) for name in (
                "transfer_id", "recipient_id", "source_npc_id", "source_memory_id",
                "source_event_id", "communication_event_id", "source_tick",
                "transfer_tick", "account", "source_role", "confidence")}
            for x in self.records]}, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != 1:
                raise ValueError("unsupported experience-transfer schema")
            result = cls(tuple(ReportedExperience(**x) for x in raw["records"]))
            if result.to_json() != payload:
                raise ValueError("snapshot must use canonical JSON")
            return result
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid experience-transfer snapshot") from exc


class NPCExperienceTransferLedger:
    """Append-only reported-experience records validated against source evidence."""
    def __init__(self, events: WorldEventLedger, history: NPCLifeHistory, snapshot=None):
        if not isinstance(events, WorldEventLedger):
            raise TypeError("events must be a WorldEventLedger")
        if not isinstance(history, NPCLifeHistory):
            raise TypeError("history must be an NPCLifeHistory")
        self.events, self.history = events, history
        self._records = {}
        if snapshot is not None:
            if not isinstance(snapshot, ExperienceTransferSnapshot):
                raise TypeError("snapshot must be an ExperienceTransferSnapshot")
            for record in snapshot.records:
                self._validate(record)
                self._insert(record)

    def _validate(self, record):
        memory = next((m for m in self.history.memories(record.source_npc_id)
                       if m.memory_id == record.source_memory_id), None)
        if memory is None:
            raise ValueError("transfer requires a source-owned autobiographical memory")
        if memory.event_id != record.source_event_id or memory.tick != record.source_tick:
            raise ValueError("transfer source memory provenance does not match")
        source = self.events.get(record.source_event_id)
        if source.tick != record.source_tick:
            raise ValueError("source event tick does not match memory")
        role = ("participant" if record.source_npc_id in source.participants else
                "witness" if record.source_npc_id in source.witnesses else "")
        if role != record.source_role:
            raise ValueError("source role does not match authoritative event")
        communication = self.events.get(record.communication_event_id)
        if communication.tick != record.transfer_tick:
            raise ValueError("communication event tick does not match transfer")
        if (record.source_npc_id not in communication.participants or
                record.recipient_id not in communication.participants):
            raise ValueError("communication event must include source and recipient")
        if communication.tick < source.tick:
            raise ValueError("communication cannot precede source experience")

    def _insert(self, record):
        prior = self._records.get(record.transfer_id)
        if prior is not None and prior != record:
            raise ValueError("transfer ID reused with different content")
        if prior is None and any(
            (x.recipient_id, x.source_npc_id, x.source_memory_id, x.communication_event_id) ==
            (record.recipient_id, record.source_npc_id, record.source_memory_id, record.communication_event_id)
            for x in self._records.values()
        ):
            raise ValueError("experience has already been transferred in this communication")
        self._records.setdefault(record.transfer_id, record)
        return self._records[record.transfer_id]

    def transfer(self, transfer_id, recipient_id, source_npc_id, source_memory_id,
                 communication_event_id, *, confidence):
        memory = next((m for m in self.history.memories(source_npc_id)
                       if m.memory_id == source_memory_id), None)
        if memory is None:
            raise ValueError("transfer requires a source-owned autobiographical memory")
        source = self.events.get(memory.event_id)
        role = ("participant" if source_npc_id in source.participants else
                "witness" if source_npc_id in source.witnesses else "")
        communication = self.events.get(communication_event_id)
        record = ReportedExperience(
            transfer_id, recipient_id, source_npc_id, source_memory_id, memory.event_id,
            communication_event_id, memory.tick, communication.tick, memory.interpretation,
            role, confidence)
        self._validate(record)
        return self._insert(record)

    def received_by(self, recipient_id):
        return tuple(sorted((x for x in self._records.values() if x.recipient_id == recipient_id),
                            key=lambda x: (x.transfer_tick, x.transfer_id)))

    def snapshot(self):
        return ExperienceTransferSnapshot(tuple(self._records[k] for k in sorted(self._records)))


@dataclass(frozen=True)
class StrategicExperienceEvidence:
    """A decision-time view; it never changes the underlying historical record."""
    owner_id: str
    evidence_id: str
    event_id: str
    tick: int
    account: str
    source_class: str
    confidence: float
    influence: float
    tags: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ("owner_id", "evidence_id", "event_id", "account", "source_class"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.source_class not in ("personal", "witnessed", "reported"):
            raise ValueError("invalid strategic evidence source class")
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if (not isinstance(self.tags, tuple) or any(not isinstance(tag, str) or not tag.strip() for tag in self.tags)
                or len(set(self.tags)) != len(self.tags)):
            raise ValueError("tags must be unique non-empty strings in a tuple")
        for name in ("confidence", "influence"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value <= 1):
                raise ValueError(f"{name} must be finite and in [0, 1]")


def strategic_experience_evidence(history: NPCLifeHistory,
                                  transfers: NPCExperienceTransferLedger,
                                  owner_id: str, current_tick: int,
                                  *, limit: int = 100) -> tuple[StrategicExperienceEvidence, ...]:
    """Retrieve grounded past experiences with conservative source-class weights.

    Personal participation has weight 1.0, witnessed events 0.6, and reported
    accounts 0.35 multiplied by the confidence assigned at transfer. Future
    memories and reports are excluded. Results are stable and bounded.
    """
    if not isinstance(history, NPCLifeHistory) or not isinstance(transfers, NPCExperienceTransferLedger):
        raise TypeError("history and transfers must be their corresponding ledgers")
    if transfers.history is not history:
        raise ValueError("experience transfer and retrieval must share one life history")
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise ValueError("owner_id must be a non-empty string")
    if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
        raise ValueError("current_tick must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")

    evidence = []
    for memory in history.memories(owner_id):
        if memory.tick > current_tick:
            continue
        event = transfers.events.get(memory.event_id)
        if owner_id in event.participants:
            source_class, weight = "personal", 1.0
        elif owner_id in event.witnesses:
            source_class, weight = "witnessed", 0.6
        else:
            continue
        evidence.append(StrategicExperienceEvidence(
            owner_id, memory.memory_id, memory.event_id, memory.tick,
            memory.interpretation, source_class, 1.0, weight, memory.tags))

    for report in transfers.received_by(owner_id):
        if report.transfer_tick > current_tick:
            continue
        evidence.append(StrategicExperienceEvidence(
            owner_id, report.transfer_id, report.source_event_id,
            report.transfer_tick, report.account, "reported",
            report.confidence, 0.35 * report.confidence,
            next(m.tags for m in history.memories(report.source_npc_id) if m.memory_id == report.source_memory_id)))

    evidence.sort(key=lambda x: (-x.tick, -x.influence, x.evidence_id))
    return tuple(evidence[:limit])


def experience_action_guidance(history: NPCLifeHistory,
                               transfers: NPCExperienceTransferLedger,
                               owner_id: str, current_tick: int, actions,
                               *, limit: int = 100) -> tuple[dict[str, float], dict[str, tuple[str, ...]]]:
    """Project explicitly tagged outcome memories onto matching actions.

    Action tags match memory tags exactly. Memories must carry exactly one
    polarity tag: outcome:success or outcome:failure. Evidence is deduplicated
    by original event per action, retaining its strongest source.
    """
    evidence = strategic_experience_evidence(history, transfers, owner_id,
                                             current_tick, limit=limit)
    source_memories = {m.memory_id: m for m in history.memories()}
    reports = {r.transfer_id: r for r in transfers.snapshot().records}
    reliability = {}
    evidence_ids = {}
    for action_id, action in sorted(actions.items()):
        action_tags = set(action.experience_tags)
        if not action_tags:
            continue
        matched = {}
        for item in evidence:
            memory_id = (item.evidence_id if item.source_class != "reported"
                         else reports[item.evidence_id].source_memory_id)
            tags = set(source_memories[memory_id].tags)
            outcomes = tags & {"outcome:success", "outcome:failure"}
            if len(outcomes) != 1 or not (action_tags & (tags - outcomes)):
                continue
            prior = matched.get(item.event_id)
            if prior is None or item.influence > prior.influence:
                matched[item.event_id] = item
        if not matched:
            continue
        weighted_delta = 0.0
        total_weight = 0.0
        ids = []
        for item in sorted(matched.values(), key=lambda x: (x.event_id, x.evidence_id)):
            memory_id = (item.evidence_id if item.source_class != "reported"
                         else reports[item.evidence_id].source_memory_id)
            tags = set(source_memories[memory_id].tags)
            polarity = 1.0 if "outcome:success" in tags else -1.0
            weighted_delta += item.influence * polarity * 0.5
            total_weight += item.influence
            ids.append(item.evidence_id)
        reliability[action_id] = min(1.0, max(0.0, (0.5 + weighted_delta) / (1.0 + total_weight)))
        evidence_ids[action_id] = tuple(sorted(ids))
    return reliability, evidence_ids


def experience_goal_guidance(history: NPCLifeHistory,
                              transfers: NPCExperienceTransferLedger,
                              owner_id: str, current_tick: int, goals,
                              *, limit: int = 100):
    """Return bounded, read-only goal priority adjustments and their provenance.

    Goals opt in through comma-separated exact tags in
    goal.metadata["experience_tags"]. Memories must carry one explicit
    goal:success or goal:failure marker plus a matching tag. Action outcome
    memories are deliberately not treated as goal outcome evidence.
    """
    evidence = strategic_experience_evidence(history, transfers, owner_id,
                                             current_tick, limit=limit)
    memories = {m.memory_id: m for m in history.memories()}
    reports = {r.transfer_id: r for r in transfers.snapshot().records}
    adjustments, evidence_ids, sources = {}, {}, {}
    for goal in sorted(goals.goals.values(), key=lambda item: item.goal_id):
        if goal.owner_id != owner_id:
            continue
        tags = {tag.strip() for tag in goal.metadata.get("experience_tags", "").split(",")
                if tag.strip()}
        if not tags:
            continue
        matched = {}
        for item in evidence:
            memory_id = (item.evidence_id if item.source_class != "reported"
                         else reports[item.evidence_id].source_memory_id)
            memory_tags = set(memories[memory_id].tags)
            outcomes = memory_tags & {"goal:success", "goal:failure"}
            if len(outcomes) != 1 or not (tags & (memory_tags - outcomes)):
                continue
            prior = matched.get(item.event_id)
            if prior is None or item.influence > prior.influence:
                matched[item.event_id] = item
        if not matched:
            continue
        delta, total = 0.0, 0.0
        ids = []
        for item in sorted(matched.values(), key=lambda x: (x.event_id, x.evidence_id)):
            memory_id = (item.evidence_id if item.source_class != "reported"
                         else reports[item.evidence_id].source_memory_id)
            polarity = 1.0 if "goal:success" in memories[memory_id].tags else -1.0
            delta += item.influence * polarity
            total += item.influence
            ids.append(item.evidence_id)
        adjustments[goal.goal_id] = max(-0.25, min(0.25, 0.25 * delta / (1.0 + total)))
        evidence_ids[goal.goal_id] = tuple(sorted(ids))
        for item in matched.values():
            sources[item.evidence_id] = item.source_class
    return adjustments, evidence_ids, sources
