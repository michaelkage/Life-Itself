"""Persistent health, obligations, finite campaign lives, ghost limits, and world archives.

Engine-independent reference implementation. All time values are simulation days;
call advance_day once per completed simulated day. World snapshots are immutable
copies so starting a new life never overwrites the world left by a dead character.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from copy import deepcopy
from typing import Any
import json
import uuid


class LifeState(str, Enum):
    ACTIVE = "active"
    SPECTATOR = "spectator"
    GHOST = "ghost"
    ARCHIVED = "archived"


@dataclass
class HealthCondition:
    condition_id: str
    kind: str
    severity: float
    recovery_per_day: float = 0.0
    persistent: bool = True
    activity_limits: dict[str, float] = field(default_factory=dict)
    days_present: int = 0

    def __post_init__(self) -> None:
        self.severity = min(1.0, max(0.0, float(self.severity)))
        self.recovery_per_day = min(1.0, max(0.0, float(self.recovery_per_day)))
        self.activity_limits = {
            str(k): min(1.0, max(0.0, float(v)))
            for k, v in self.activity_limits.items()
        }


@dataclass
class SocialObligation:
    obligation_id: str
    debtor_id: str
    creditor_id: str
    money_due: float = 0.0
    stress_delta: float = 0.0
    trust_delta_on_settlement: float = 0.05
    due_day: int = 0
    settled: bool = False
    missed: bool = False


@dataclass
class CharacterHealth:
    character_id: str
    conditions: list[HealthCondition] = field(default_factory=list)
    stress: float = 0.0

    def activity_capacity(self, activity: str) -> float:
        """Return the most restrictive condition's capacity for an activity."""
        capacity = 1.0
        for condition in self.conditions:
            if condition.severity <= 0:
                continue
            limit = condition.activity_limits.get(activity, 1.0)
            capacity = min(capacity, 1.0 - condition.severity * (1.0 - limit))
        return max(0.0, min(1.0, capacity))

    def advance_day(self) -> None:
        for condition in self.conditions:
            condition.days_present += 1
            condition.severity = max(0.0, condition.severity - condition.recovery_per_day)
        self.conditions = [c for c in self.conditions if c.severity > 0 or c.persistent]


@dataclass
class CampaignLife:
    character_id: str
    state: LifeState = LifeState.ACTIVE
    started_day: int = 0
    death_day: int | None = None
    death_cause: str | None = None
    ghost_influence_uses: int = 0
    last_ghost_influence_day: int | None = None


@dataclass
class WorldArchive:
    archive_id: str
    day: int
    reason: str
    world_state: dict[str, Any]


@dataclass
class PersistentWorld:
    day: int = 0
    money: dict[str, float] = field(default_factory=dict)
    trust: dict[str, float] = field(default_factory=dict)
    stress: dict[str, float] = field(default_factory=dict)
    health: dict[str, CharacterHealth] = field(default_factory=dict)
    obligations: list[SocialObligation] = field(default_factory=list)
    life: CampaignLife | None = None
    archives: list[WorldArchive] = field(default_factory=list)
    world_flags: dict[str, Any] = field(default_factory=dict)

    def add_obligation(self, obligation: SocialObligation) -> None:
        if any(o.obligation_id == obligation.obligation_id for o in self.obligations):
            raise ValueError(f"duplicate obligation id: {obligation.obligation_id}")
        if obligation.money_due < 0:
            raise ValueError("money_due cannot be negative")
        self.obligations.append(obligation)

    def settle_obligation(self, obligation_id: str) -> bool:
        obligation = self._obligation(obligation_id)
        if obligation.settled or obligation.missed:
            return False
        available = self.money.get(obligation.debtor_id, 0.0)
        if available < obligation.money_due:
            return False
        self.money[obligation.debtor_id] = available - obligation.money_due
        obligation.settled = True
        self.stress[obligation.debtor_id] = max(
            0.0, self.stress.get(obligation.debtor_id, 0.0) + obligation.stress_delta
        )
        key = self._trust_key(obligation.debtor_id, obligation.creditor_id)
        self.trust[key] = min(1.0, max(-1.0, self.trust.get(key, 0.0) + obligation.trust_delta_on_settlement))
        return True

    def _obligation(self, obligation_id: str) -> SocialObligation:
        for obligation in self.obligations:
            if obligation.obligation_id == obligation_id:
                return obligation
        raise KeyError(obligation_id)

    @staticmethod
    def _trust_key(a: str, b: str) -> str:
        return f"{a}->{b}"

    def advance_day(self) -> None:
        self.day += 1
        for health in self.health.values():
            health.advance_day()
        for obligation in self.obligations:
            if not obligation.settled and not obligation.missed and obligation.due_day < self.day:
                obligation.missed = True
                self.stress[obligation.debtor_id] = max(
                    0.0, self.stress.get(obligation.debtor_id, 0.0) + abs(obligation.stress_delta) + 0.1
                )
                key = self._trust_key(obligation.debtor_id, obligation.creditor_id)
                self.trust[key] = max(-1.0, self.trust.get(key, 0.0) - 0.15)

    def kill_current_life(self, cause: str) -> WorldArchive:
        if self.life is None or self.life.state is not LifeState.ACTIVE:
            raise RuntimeError("only an active life can die")
        self.life.state = LifeState.SPECTATOR
        self.life.death_day = self.day
        self.life.death_cause = cause
        archive = WorldArchive(
            archive_id=str(uuid.uuid4()),
            day=self.day,
            reason=f"death:{cause}",
            world_state=self._world_state_copy(),
        )
        self.archives.append(archive)
        return archive

    def enter_ghost_state(self) -> None:
        if self.life is None or self.life.state is not LifeState.SPECTATOR:
            raise RuntimeError("ghost state is available only after death")
        self.life.state = LifeState.GHOST

    def ghost_influence(self, *, allowed_window: bool, cooldown_days: int = 7) -> bool:
        """Ghosts may influence the world only in explicit windows, once per cooldown."""
        if self.life is None or self.life.state is not LifeState.GHOST:
            return False
        if not allowed_window:
            return False
        last = self.life.last_ghost_influence_day
        if last is not None and self.day - last < cooldown_days:
            return False
        self.life.ghost_influence_uses += 1
        self.life.last_ghost_influence_day = self.day
        return True

    def start_new_life(self, character_id: str) -> None:
        if self.life is not None and self.life.state is LifeState.ACTIVE:
            raise RuntimeError("cannot replace an active life")
        if self.life is not None:
            self.life.state = LifeState.ARCHIVED
        self.life = CampaignLife(character_id=character_id, started_day=self.day)
        self.health.setdefault(character_id, CharacterHealth(character_id))
        self.money.setdefault(character_id, 0.0)
        self.stress.setdefault(character_id, 0.0)

    def _world_state_copy(self) -> dict[str, Any]:
        return deepcopy({
            "day": self.day, "money": self.money, "trust": self.trust,
            "stress": self.stress, "health": self.health,
            "obligations": self.obligations, "life": self.life,
            "world_flags": self.world_flags,
        })

    def to_json(self) -> str:
        """Serialize with a version marker; enum values are stable strings."""
        def encode(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if hasattr(obj, "__dataclass_fields__"):
                return {k: encode(v) for k, v in obj.__dict__.items()}
            if isinstance(obj, dict):
                return {k: encode(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [encode(v) for v in obj]
            return obj
        return json.dumps({"schema_version": 1, "world": encode(self)}, sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "PersistentWorld":
        raw = json.loads(payload)
        if raw.get("schema_version") != 1:
            raise ValueError("unsupported save schema version")
        data = raw["world"]
        health = {
            key: CharacterHealth(
                character_id=value["character_id"],
                conditions=[HealthCondition(**c) for c in value.get("conditions", [])],
                stress=value.get("stress", 0.0),
            )
            for key, value in data.get("health", {}).items()
        }
        obligations = [SocialObligation(**o) for o in data.get("obligations", [])]
        life_data = data.get("life")
        life = CampaignLife(**{**life_data, "state": LifeState(life_data["state"])}) if life_data else None
        archives = [
            WorldArchive(**a) for a in data.get("archives", [])
        ]
        return cls(
            day=data.get("day", 0), money=data.get("money", {}), trust=data.get("trust", {}),
            stress=data.get("stress", {}), health=health, obligations=obligations,
            life=life, archives=archives, world_flags=data.get("world_flags", {}),
        )
