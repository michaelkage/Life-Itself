"""Durable, cross-process population-tick transaction journal.

Participants expose canonical JSON checkpoints. A PREPARED record is fsynced
before simulation mutations; COMMITTED is fsynced only after every participant's
post-state and result envelope are durable. Recovery restores pre-state for an
interrupted transaction and post-state for a committed transaction.

The journal is protected by an OS-level advisory lock as well as an in-process
reentrant lock. Every operation reloads the journal while holding that lock, so
independent workers cannot make decisions from stale transaction history.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
import time
from typing import Callable, Iterable

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows CI
    fcntl = None
    import msvcrt


def _canonical(value) -> str:
    def encode(item):
        if hasattr(item, "__dataclass_fields__"):
            return {name: encode(getattr(item, name)) for name in item.__dataclass_fields__}
        if isinstance(item, Enum):
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
    """Serialize ticks with process-safe locking, durable prepare/commit and recovery.

    Participant checkpoints must include all mutable state and replay indexes
    owned by that subsystem. Participants restore in reverse registration order
    during rollback and forward order during committed recovery.

    The journal lock serializes coordinators sharing the same journal path. A
    caller must still ensure that participant state itself is not concurrently
    mutated outside this coordinator while a transaction is running.
    """

    SCHEMA_VERSION = 2

    def __init__(
        self,
        journal_path: str | os.PathLike,
        participants: Iterable[TransactionParticipant],
        *,
        lock_timeout_seconds: float = 30.0,
        history_limit: int = 64,
    ):
        self.path = Path(journal_path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.participants = tuple(participants)
        if not self.participants or any(not isinstance(p, TransactionParticipant) for p in self.participants):
            raise ValueError("at least one valid transaction participant is required")
        names = [p.name for p in self.participants]
        if len(names) != len(set(names)):
            raise ValueError("transaction participant names must be unique")
        if isinstance(lock_timeout_seconds, bool) or not isinstance(lock_timeout_seconds, (int, float)) or lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be a positive finite number")
        if not float(lock_timeout_seconds) < float("inf"):
            raise ValueError("lock_timeout_seconds must be finite")
        self.lock_timeout_seconds = float(lock_timeout_seconds)
        if isinstance(history_limit, bool) or not isinstance(history_limit, int) or history_limit < 1:
            raise ValueError("history_limit must be a positive integer")
        self.history_limit = history_limit
        self._lock = RLock()
        self._records: dict[int, dict] = {}
        self._needs_recovery = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._journal_lock():
            if self.path.exists():
                self._load()
            self._recover_locked()

    @contextmanager
    def _journal_lock(self):
        """Acquire a bounded exclusive OS lock shared by all coordinator processes."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(self.lock_path, "a+b")
        acquired = False
        deadline = time.monotonic() + self.lock_timeout_seconds
        try:
            if fcntl is not None:
                while True:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        acquired = True
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"timed out acquiring population journal lock: {self.lock_path}")
                        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            else:  # pragma: no cover - exercised on Windows CI
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write(b"\\0")
                    stream.flush()
                while True:
                    try:
                        stream.seek(0)
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                        acquired = True
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"timed out acquiring population journal lock: {self.lock_path}")
                        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            yield
        finally:
            if acquired:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                else:  # pragma: no cover - exercised on Windows CI
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            stream.close()

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
        # Keep a bounded replay window. The newest record always retains a full
        # post-checkpoint, so older committed snapshots are not needed for
        # restart recovery. Ticks older than this window are rejected as stale.
        if len(self._records) > self.history_limit:
            retained_ticks = sorted(self._records)[-self.history_limit:]
            self._records = {
                tick: self._records[tick]
                for tick in retained_ticks
            }
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
            if os.name == "nt":  # directory handles cannot be fsynced portably on Windows
                return
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
        if not isinstance(raw, dict) or raw.get("schema_version") not in (1, self.SCHEMA_VERSION) or not isinstance(raw.get("records"), list):
            raise ValueError("unsupported or malformed population transaction journal")
        legacy = raw["schema_version"] == 1
        expected = {participant.name for participant in self.participants}
        records = {}
        previous_tick = -1
        for item in raw["records"]:
            if not isinstance(item, dict):
                raise ValueError("population transaction journal records must be objects")
            tick = item.get("tick")
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0 or tick in records:
                raise ValueError("invalid or duplicate population transaction tick")
            if tick <= previous_tick:
                raise ValueError("population transaction records must be ordered by tick")
            previous_tick = tick
            status = item.get("status")
            if status not in ("prepared", "committed", "aborted"):
                raise ValueError("invalid population transaction status")
            signature = item.get("request_signature")
            if not isinstance(signature, str) or len(signature) != 64 or any(ch not in "0123456789abcdef" for ch in signature):
                raise ValueError("invalid population transaction request signature")
            before = item.get("before")
            if not isinstance(before, dict) or set(before) != expected:
                raise ValueError("population transaction pre-checkpoint participant set does not match runtime")
            for name, checkpoint in before.items():
                if not isinstance(checkpoint, str):
                    raise ValueError(f"invalid pre-checkpoint for participant {name}")
                json.loads(checkpoint)
            after = item.get("after", {})
            if status == "committed":
                if not isinstance(after, dict) or set(after) != expected:
                    raise ValueError("committed post-checkpoint participant set does not match runtime")
                for name, checkpoint in after.items():
                    if not isinstance(checkpoint, str):
                        raise ValueError(f"invalid post-checkpoint for participant {name}")
                    json.loads(checkpoint)
                result_payload = item.get("result_payload")
                result_digest = item.get("result_digest")
                if legacy and result_payload is None:
                    item["result_payload"] = "null"
                    item["result_digest"] = sha256(b"null").hexdigest()
                    item["result_reconstructed"] = True
                else:
                    if not isinstance(result_payload, str) or not isinstance(result_digest, str):
                        raise ValueError("committed population transaction is missing its result envelope")
                    actual_digest = sha256(result_payload.encode("utf-8")).hexdigest()
                    if actual_digest != result_digest:
                        raise ValueError("committed population transaction result digest mismatch")
                    json.loads(result_payload)
            elif status == "prepared":
                if not isinstance(after, dict) or after:
                    raise ValueError("prepared transaction cannot contain post-checkpoints")
            else:
                if not isinstance(after, dict) or after:
                    raise ValueError("aborted transaction cannot contain post-checkpoints")
            records[tick] = item
        self._records = records
        if legacy:
            self._persist()

    def _recover_locked(self) -> tuple[int, ...]:
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
        self._needs_recovery = False
        return tuple(recovered)

    def recover(self) -> tuple[int, ...]:
        """Reload the durable journal and recover incomplete transactions."""
        with self._lock, self._journal_lock():
            if self.path.exists():
                self._load()
            else:
                self._records = {}
            return self._recover_locked()

    def execute(self, tick: int, request, operation: Callable[[], object]):
        """Execute once atomically; replay restores committed state before rebuilding output."""
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValueError("tick must be a non-negative integer")
        if not callable(operation):
            raise TypeError("operation must be callable")
        signature = sha256(_canonical(request).encode("utf-8")).hexdigest()
        with self._lock, self._journal_lock():
            if self._needs_recovery:
                raise RuntimeError("population transaction coordinator requires journal recovery")
            if self.path.exists():
                self._load()
            else:
                self._records = {}
            self._recover_locked()

            existing = self._records.get(tick)
            if existing is not None:
                if existing["request_signature"] != signature:
                    raise ValueError(f"population transaction {tick} replayed with different inputs")
                if existing["status"] == "committed":
                    self._restore(existing["after"])
                    return operation()
                if existing["status"] == "prepared":
                    raise RuntimeError(f"population transaction {tick} is awaiting crash recovery")
                if tick != max(self._records):
                    raise ValueError("only the latest aborted population transaction can be retried")
                del self._records[tick]
                self._persist()

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
                "result_payload": None,
            }
            self._records[tick] = record
            try:
                self._persist()
            except BaseException:
                self._records.pop(tick, None)
                self._needs_recovery = True
                raise

            try:
                result = operation()
                after = self._capture()
                result_payload = _canonical(result)
            except BaseException:
                try:
                    self._restore(before, reverse=True)
                    record["status"] = "aborted"
                    record["after"] = {}
                    self._persist()
                except BaseException:
                    self._needs_recovery = True
                    raise
                raise

            record["after"] = after
            record["result_digest"] = sha256(result_payload.encode("utf-8")).hexdigest()
            record["result_payload"] = result_payload
            record["status"] = "committed"
            try:
                self._persist()
            except BaseException:
                # Atomic replacement may already have installed COMMITTED even
                # when a later fsync fails. Never roll memory back to PREPARED;
                # require an explicit journal reload/recovery to resolve outcome.
                self._needs_recovery = True
                raise
            return result

    @property
    def participant_names(self) -> frozenset[str]:
        return frozenset(participant.name for participant in self.participants)

    def journal_snapshot(self) -> tuple[dict, ...]:
        """Return detached journal records after synchronizing with other workers."""
        with self._lock, self._journal_lock():
            if self.path.exists():
                self._load()
            else:
                self._records = {}
            return tuple(json.loads(json.dumps(self._records[tick])) for tick in sorted(self._records))
