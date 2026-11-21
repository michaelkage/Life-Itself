"""Durable, cross-subsystem population-tick transaction journal.

Participants expose canonical JSON checkpoints. A PREPARED record is fsynced
before simulation mutations; COMMITTED is fsynced only after every participant's
post-state and result envelope are durable. Recovery restores pre-state for an
interrupted transaction and post-state for a committed transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Callable, Iterable


def _canonical(value) -> str:
    def encode(item):
        if hasattr(item, "__dataclass_fields__"):
            return {name: encode(getattr(item, name)) for name in item.__dataclass_fields__}
        if hasattr(item, "value") and type(item).__module__ == "enum":
            return encode(item.value)
        if isinstance(item, dict):
            return {str(key): encode(item[key]) for key in sorted(item, key=lambda k: str(k))}
        if isinstance(item, (set, frozenset)):
            return sorted((encode(value) for value in item), key=lambda x: json.dumps(x, sort_keys=True))
        if isinstance(item, (tuple, list)):
            return [encode(value) for value in item]
        if isinstance(item, float):
            if item != item or item in (float("inf"), float("-inf")):
                raise ValueError("transaction inputs cannot contain non-finite numbers")
        if item is None or isinstance(item, (str, int, float, bool)):
            return item
        raise TypeError(f"unsupported transaction value: {type(item).__name__}")
    return json.dumps(encode(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class TransactionParticipant:
    """A named subsystem with a canonical JSON checkpoint and restore operation."""
    name: str
    capture: Callable[[], str]
    restore: Callable[[str], None]

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("participant name must be non-empty")
        if not callable(self.capture) or not callable(self.restore):
            raise TypeError("participant capture and restore must be callable")


class PopulationTickTransactionCoordinator:
    """Serialize population ticks with durable prepare/commit and restart recovery.

    Each participant checkpoint must include all mutable state and replay indexes
    owned by that subsystem. Participants are restored in reverse registration
    order during rollback and forward order during committed recovery.
    """

    SCHEMA_VERSION = 1

    def __init__(self, journal_path: str | os.PathLike, participants: Iterable[TransactionParticipant]):
        self.path = Path(journal_path)
        self.participants = tuple(participants)
        if not self.participants or any(not isinstance(p, TransactionParticipant) for p in self.participants):
            raise ValueError("at least one valid transaction participant is required")
        names = [p.name for p in self.participants]
        if len(names) != len(set(names)):
            raise ValueError("transaction participant names must be unique")
        self._lock = RLock()
        self._records: dict[int, dict] = {}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()
        self.recover()

    def _capture(self) -> dict[str, str]:
        values = {}
        for participant in self.participants:
            payload = participant.capture()
            if not isinstance(payload, str):
                raise TypeError(f"participant {participant.name} must return a JSON string")
            parsed = json.loads(payload)
            values[participant.name] = json.dumps(parsed, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return values

    def _restore(self, checkpoints: dict[str, str], reverse: bool = False) -> None:
        sequence = reversed(self.participants) if reverse else self.participants
        for participant in sequence:
            if participant.name not in checkpoints:
                raise ValueError(f"journal is missing participant checkpoint: {participant.name}")
            participant.restore(checkpoints[participant.name])

    def _persist(self) -> None:
        payload = json.dumps({
            "schema_version": self.SCHEMA_VERSION,
            "records": [self._records[tick] for tick in sorted(self._records)],
        }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != self.SCHEMA_VERSION or not isinstance(raw.get("records"), list):
            raise ValueError("unsupported or malformed population transaction journal")
        records = {}
        for item in raw["records"]:
            tick = item.get("tick")
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0 or tick in records:
                raise ValueError("invalid or duplicate population transaction tick")
            if item.get("status") not in ("prepared", "committed", "aborted"):
                raise ValueError("invalid population transaction status")
            if not isinstance(item.get("request_signature"), str) or len(item["request_signature"]) != 64:
                raise ValueError("invalid population transaction request signature")
            records[tick] = item
        self._records = records

    def recover(self) -> tuple[int, ...]:
        """Recover incomplete transactions and restore latest committed state."""
        with self._lock:
            recovered = []
            for tick in sorted(self._records):
                record = self._records[tick]
                if record["status"] == "prepared":
                    self._restore(record["before"], reverse=True)
                    record["status"] = "aborted"
                    recovered.append(tick)
                elif record["status"] == "committed":
                    self._restore(record["after"])
            if recovered:
                self._persist()
            return tuple(recovered)

    def execute(self, tick: int, request, operation: Callable[[], object]):
        """Execute once atomically; replay restores committed state before rebuilding output."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not callable(operation):
            raise TypeError("operation must be callable")
        signature = sha256(_canonical(request).encode("utf-8")).hexdigest()
        with self._lock:
            existing = self._records.get(tick)
            if existing is not None:
                if existing["request_signature"] != signature:
                    raise ValueError(f"population transaction {tick} replayed with different inputs")
                if existing["status"] != "committed":
                    raise RuntimeError(f"population transaction {tick} did not commit; retry requires a new tick")
                self._restore(existing["after"])
                return operation()

            if self._records and tick <= max(self._records):
                raise ValueError("new population transactions must have strictly increasing ticks")
            before = self._capture()
            record = {
                "tick": tick,
                "request_signature": signature,
                "status": "prepared",
                "before": before,
                "after": {},
                "result_digest": None,
            }
            self._records[tick] = record
            self._persist()
            try:
                result = operation()
                after = self._capture()
                result_payload = _canonical(result)
                record["after"] = after
                record["result_digest"] = sha256(result_payload.encode("utf-8")).hexdigest()
                record["status"] = "committed"
                self._persist()
                return result
            except BaseException:
                self._restore(before, reverse=True)
                record["status"] = "aborted"
                record["after"] = {}
                self._persist()
                raise

    def journal_snapshot(self) -> tuple[dict, ...]:
        with self._lock:
            return tuple(json.loads(json.dumps(self._records[tick])) for tick in sorted(self._records))
