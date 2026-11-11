"""Provenance-preserving autobiographical memory for long-term NPC intentions.

This ledger stores compact, immutable links between goals and evidence already
recorded by the simulation. It never invents motives: lifecycle reasons,
commitment rationales, plan outcomes, and autobiographical interpretations are
copied only from their authoritative source records.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable

from .npc_life_history import NPCLifeHistory
from .npc_goal_emergence import GoalLifecycleLedger
from .goal_arbitration import GoalCommitmentLedger
from .action_evaluation import ActionPlanEvaluationLedger
from .goals import GoalBook


def _text(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _identity_digest(owner_id: str, goal_id: str, tick: int,
                     memory_type: str, source_kind: str,
                     source_id: str) -> str:
    identity = json.dumps(
        [owner_id, goal_id, tick, memory_type, source_kind, source_id],
        ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class GoalIntentionMemory:
    memory_id: str
    owner_id: str
    goal_id: str
    tick: int
    memory_type: str
    source_kind: str
    source_id: str
    content: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("memory_id", "owner_id", "goal_id", "memory_type",
                     "source_kind", "source_id", "content"):
            _text(name, getattr(self, name))
        if isinstance(self.tick, bool) or not isinstance(self.tick, int) or self.tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if self.memory_type not in {
            "adopted", "reopened", "completed", "failed", "abandoned",
            "blocked", "committed", "deferred", "plan_completed",
            "plan_failed", "plan_replanned", "personal_experience",
        }:
            raise ValueError("unsupported intention memory type")
        if self.source_kind not in {"goal_lifecycle", "goal_commitment",
                                    "plan_evaluation", "autobiographical_memory"}:
            raise ValueError("unsupported intention memory source kind")
        if not isinstance(self.evidence_ids, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.evidence_ids
        ):
            raise ValueError("evidence_ids must be a tuple of non-empty strings")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids must be unique")
        expected = _identity_digest(
            self.owner_id, self.goal_id, self.tick, self.memory_type,
            self.source_kind, self.source_id,
        )
        if self.memory_id != "goal-memory:" + expected:
            raise ValueError("memory_id does not match its deterministic source identity")


class GoalIntentionMemoryLedger:
    """Append-only per-NPC intention history with deterministic replay."""

    def __init__(self, entries: Iterable[GoalIntentionMemory] = ()) -> None:
        self._entries: dict[str, GoalIntentionMemory] = {}
        self._source_keys: dict[tuple[str, str, str, str], str] = {}
        for entry in sorted(tuple(entries), key=lambda item: (item.tick, item.memory_id)):
            self.record(entry)

    @staticmethod
    def make(owner_id: str, goal_id: str, tick: int, memory_type: str,
             source_kind: str, source_id: str, content: str,
             evidence_ids: tuple[str, ...] = ()) -> GoalIntentionMemory:
        digest = _identity_digest(
            owner_id, goal_id, tick, memory_type, source_kind, source_id,
        )
        return GoalIntentionMemory(
            "goal-memory:" + digest, owner_id, goal_id, tick, memory_type,
            source_kind, source_id, content, tuple(evidence_ids),
        )

    def record(self, entry: GoalIntentionMemory) -> GoalIntentionMemory:
        if not isinstance(entry, GoalIntentionMemory):
            raise TypeError("entry must be GoalIntentionMemory")
        existing = self._entries.get(entry.memory_id)
        if existing is not None:
            if existing != entry:
                raise ValueError("intention memory ID reused with conflicting content")
            return existing
        key = (entry.owner_id, entry.goal_id, entry.source_kind, entry.source_id)
        prior_id = self._source_keys.get(key)
        if prior_id is not None:
            prior = self._entries[prior_id]
            if prior != entry:
                raise ValueError("one source cannot produce conflicting intention memories")
            return prior
        if any(item.owner_id == entry.owner_id and item.goal_id == entry.goal_id
               and item.tick > entry.tick for item in self._entries.values()):
            raise ValueError("intention memories must be recorded chronologically per goal")
        self._entries[entry.memory_id] = entry
        self._source_keys[key] = entry.memory_id
        return entry

    def entries(self, owner_id: str | None = None,
                goal_id: str | None = None) -> tuple[GoalIntentionMemory, ...]:
        values = self._entries.values()
        if owner_id is not None:
            values = (item for item in values if item.owner_id == owner_id)
        if goal_id is not None:
            values = (item for item in values if item.goal_id == goal_id)
        return tuple(sorted(values, key=lambda item: (item.tick, item.memory_id)))

    def for_goal(self, owner_id: str, goal_id: str) -> tuple[GoalIntentionMemory, ...]:
        return self.entries(owner_id, goal_id)

    def snapshot(self) -> "GoalIntentionMemorySnapshot":
        records = tuple(
            (item.memory_id, item.owner_id, item.goal_id, item.tick,
             item.memory_type, item.source_kind, item.source_id, item.content,
             tuple(item.evidence_ids))
            for item in sorted(self._entries.values(), key=lambda value: value.memory_id)
        )
        return GoalIntentionMemorySnapshot(records)


class GoalIntentionMemoryAdapter:
    """Project existing goal and life-history evidence into intention memory."""

    @staticmethod
    def ingest(
        ledger: GoalIntentionMemoryLedger,
        *,
        goals: GoalBook,
        current_tick: int,
        lifecycle: GoalLifecycleLedger | None = None,
        commitments: GoalCommitmentLedger | None = None,
        life_history: NPCLifeHistory | None = None,
        evaluations: ActionPlanEvaluationLedger | None = None,
    ) -> tuple[GoalIntentionMemory, ...]:
        if not isinstance(ledger, GoalIntentionMemoryLedger):
            raise TypeError("ledger must be GoalIntentionMemoryLedger")
        if not isinstance(goals, GoalBook):
            raise TypeError("goals must be GoalBook")
        if isinstance(current_tick, bool) or not isinstance(current_tick, int) or current_tick < 0:
            raise ValueError("current_tick must be a non-negative integer")
        for value, expected, name in (
            (lifecycle, GoalLifecycleLedger, "lifecycle"),
            (commitments, GoalCommitmentLedger, "commitments"),
            (life_history, NPCLifeHistory, "life_history"),
            (evaluations, ActionPlanEvaluationLedger, "evaluations"),
        ):
            if value is not None and not isinstance(value, expected):
                raise TypeError(f"{name} has an invalid ledger type")

        known = {goal.goal_id: goal.owner_id for goal in goals.goals.values()}
        candidates: list[GoalIntentionMemory] = []

        if lifecycle is not None:
            for event in lifecycle.snapshot():
                if known.get(event.goal_id) != event.owner_id:
                    raise ValueError("lifecycle history references an unknown goal or owner")
                if event.tick > current_tick:
                    raise ValueError("lifecycle history cannot be from the future")
                if event.to_status == "active":
                    kind = "adopted" if event.from_status is None else "reopened"
                else:
                    kind = event.to_status
                content = event.reason
                candidates.append(ledger.make(
                    event.owner_id, event.goal_id, event.tick, kind,
                    "goal_lifecycle", event.event_id, content, event.evidence_ids,
                ))

        if commitments is not None:
            for item in commitments.entries():
                if known.get(item.selected_goal_id) != item.owner_id:
                    raise ValueError("commitment references an unknown selected goal or owner")
                if item.tick > current_tick:
                    raise ValueError("commitment history cannot be from the future")
                candidates.append(ledger.make(
                    item.owner_id, item.selected_goal_id, item.tick, "committed",
                    "goal_commitment", item.commitment_id, item.rationale,
                    (item.assessment_id,),
                ))
                for goal_id in item.deferred_goal_ids:
                    if known.get(goal_id) != item.owner_id:
                        raise ValueError("commitment references an unknown deferred goal or owner")
                    candidates.append(ledger.make(
                        item.owner_id, goal_id, item.tick, "deferred",
                        "goal_commitment", item.commitment_id,
                        "Deferred while another intention was committed",
                        (item.assessment_id,),
                    ))

        if evaluations is not None:
            for item in evaluations.plan_history:
                if known.get(item.goal_id) != item.owner_id:
                    raise ValueError("plan evaluation references an unknown goal or owner")
                if item.plan_id == "" or not item.evidence_event_ids:
                    raise ValueError("plan evaluation must retain its source evidence")
                # The evaluation ledger's execution journal supplies terminal plan ticks.
                records = [record for record in evaluations.executions.snapshot()
                           if record.execution_id.startswith(item.plan_id + ":step:")
                           and record.owner_id == item.owner_id]
                if not records:
                    raise ValueError("plan evaluation has no matching execution history")
                tick = max(record.tick for record in records)
                if tick > current_tick:
                    raise ValueError("plan evaluation cannot be from the future")
                kind = {
                    "completed": "plan_completed",
                    "failed": "plan_failed",
                    "replanned": "plan_replanned",
                }[item.terminal_status]
                detail = (
                    f"Plan {item.terminal_status}; completed actions: "
                    + (", ".join(item.completed_actions) or "none")
                    + "; failed actions: "
                    + (", ".join(item.failed_actions) or "none")
                )
                candidates.append(ledger.make(
                    item.owner_id, item.goal_id, tick, kind,
                    "plan_evaluation", item.plan_id, detail,
                    item.evidence_event_ids,
                ))

        if life_history is not None and lifecycle is not None:
            memories = {item.memory_id: item for item in life_history.memories()}
            for event in lifecycle.snapshot():
                for evidence_id in event.evidence_ids:
                    memory = memories.get(evidence_id)
                    if memory is None:
                        continue
                    if memory.owner_id != event.owner_id or memory.tick > event.tick:
                        raise ValueError("goal lifecycle autobiographical evidence has invalid owner or chronology")
                    candidates.append(ledger.make(
                        event.owner_id, event.goal_id, memory.tick,
                        "personal_experience", "autobiographical_memory",
                        memory.memory_id, memory.interpretation,
                        (memory.event_id, memory.memory_id),
                    ))

        candidates.sort(key=lambda item: (item.tick, item.memory_id))
        added = []
        for item in candidates:
            added.append(ledger.record(item))
        return tuple(added)


@dataclass(frozen=True)
class GoalIntentionMemorySnapshot:
    records: tuple[tuple[object, ...], ...]
    SCHEMA_VERSION = 1

    def __post_init__(self) -> None:
        if not isinstance(self.records, tuple) or any(
            not isinstance(record, tuple) or len(record) != 9 for record in self.records
        ):
            raise ValueError("invalid goal intention memory records")
        ids = [record[0] for record in self.records]
        if ids != sorted(set(ids)):
            raise ValueError("intention memory IDs must be unique and sorted")
        GoalIntentionMemoryLedger(
            tuple(GoalIntentionMemory(
                record[0], record[1], record[2], record[3], record[4],
                record[5], record[6], record[7], tuple(record[8]),
            ) for record in self.records)
        )

    def to_json(self) -> str:
        return json.dumps(
            {"schema_version": self.SCHEMA_VERSION,
             "records": [list(record) for record in self.records]},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )

    @classmethod
    def from_json(cls, payload: str) -> "GoalIntentionMemorySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported goal intention memory schema")
            result = cls(tuple(
                (record[0], record[1], record[2], record[3], record[4],
                 record[5], record[6], record[7], tuple(record[8]))
                for record in raw["records"]
            ))
            if result.to_json() != payload:
                raise ValueError("goal intention memory snapshot must be canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise ValueError("invalid goal intention memory snapshot") from exc

    def restore(self) -> GoalIntentionMemoryLedger:
        return GoalIntentionMemoryLedger(tuple(
            GoalIntentionMemory(
                record[0], record[1], record[2], record[3], record[4],
                record[5], record[6], record[7], tuple(record[8]),
            ) for record in self.records
        ))
