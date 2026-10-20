"""Daily health, economic, reciprocal-support, and personality-aware ghost systems.

This layer is deterministic given its inputs, so the same saved world and random
seed produce the same results. Probabilistic recovery is represented by explicit
confidence intervals rather than pretending medicine predicts an exact outcome.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from random import Random
from typing import Any

from .health_life import CharacterHealth, HealthCondition, LifeState, PersistentWorld, SocialObligation


@dataclass
class Treatment:
    treatment_id: str
    condition_id: str
    effectiveness: float
    daily_cost: float
    care_hours: float = 0.0
    complication_risk: float = 0.0
    active: bool = True


@dataclass
class RecoveryEstimate:
    condition_id: str
    expected_recovery: float
    lower_bound: float
    upper_bound: float
    complication_probability: float


@dataclass
class DailyLifeRecord:
    character_id: str
    day: int
    attended_work: bool
    wage_earned: float
    wage_lost: float
    care_hours_needed: float
    treatment_cost: float
    capacity: float


@dataclass
class PersonProfile:
    character_id: str
    personality: dict[str, float] = field(default_factory=dict)
    memories: dict[str, float] = field(default_factory=dict)
    relationships: dict[str, float] = field(default_factory=dict)
    alive: bool = True
    estate_money: float = 0.0
    care_need: float = 0.0

    def trait(self, name: str, default: float = 0.5) -> float:
        return max(0.0, min(1.0, float(self.personality.get(name, default))))


class ResponsibilityOutcome(str, Enum):
    PAID_FROM_ESTATE = "paid_from_estate"
    ASSUMED_BY_SUPPORTER = "assumed_by_supporter"
    FORGIVEN = "forgiven"
    UNRESOLVED = "unresolved"


@dataclass
class ResponsibilityResolution:
    obligation_id: str
    outcome: ResponsibilityOutcome
    responsible_person: str | None
    amount_paid: float
    trust_change: float


@dataclass
class GhostWindow:
    start_hour: float
    end_hour: float
    influence_strength: float = 1.0
    permitted_actions: tuple[str, ...] = ("sign", "sound", "dream")


@dataclass
class GhostDecision:
    accepted: bool
    npc_id: str
    action: str
    reason: str
    influence_score: float


class LifeSimulation:
    """Simulation services attached to a PersistentWorld and its NPC roster."""

    def __init__(self, world: PersistentWorld, *, seed: int = 1) -> None:
        self.world = world
        self.random = Random(seed)
        self.people: dict[str, PersonProfile] = {}
        self.treatments: dict[str, list[Treatment]] = {}
        self.recovery_estimates: dict[str, RecoveryEstimate] = {}
        self.daily_records: list[DailyLifeRecord] = []
        self.ghost_windows: list[GhostWindow] = []
        self.ghost_action_log: list[GhostDecision] = []
        self.care_providers: dict[str, list[str]] = {}
        self.resolutions: list[ResponsibilityResolution] = []

    def register_person(self, profile: PersonProfile) -> None:
        self.people[profile.character_id] = profile
        self.world.money.setdefault(profile.character_id, 0.0)
        self.world.stress.setdefault(profile.character_id, 0.0)
        self.world.health.setdefault(profile.character_id, CharacterHealth(profile.character_id))

    def estimate_recovery(self, character_id: str, condition_id: str, *,
                          treatment_id: str | None = None) -> RecoveryEstimate:
        health = self.world.health[character_id]
        condition = next(c for c in health.conditions if c.condition_id == condition_id)
        treatment_factor = 1.0
        complication = 0.0
        if treatment_id:
            treatment = next(t for t in self.treatments.get(character_id, [])
                             if t.treatment_id == treatment_id and t.active)
            treatment_factor += max(0.0, treatment.effectiveness)
            complication = max(0.0, min(1.0, treatment.complication_risk))
        base = condition.recovery_per_day * treatment_factor
        uncertainty = max(0.01, condition.severity * 0.15)
        estimate = RecoveryEstimate(condition_id, min(condition.severity, base),
                                    max(0.0, base - uncertainty),
                                    min(condition.severity, base + uncertainty), complication)
        self.recovery_estimates[f"{character_id}:{condition_id}"] = estimate
        return estimate

    def prescribe_treatment(self, character_id: str, treatment: Treatment) -> bool:
        health = self.world.health[character_id]
        if not any(c.condition_id == treatment.condition_id for c in health.conditions):
            raise KeyError(treatment.condition_id)
        if self.world.money.get(character_id, 0.0) < treatment.daily_cost:
            return False
        self.treatments.setdefault(character_id, []).append(treatment)
        return True

    def _condition_capacity(self, health: CharacterHealth, activity: str) -> float:
        return health.activity_capacity(activity)

    def simulate_day(self, *, wages: dict[str, float] | None = None,
                     work_threshold: float = 0.55) -> list[DailyLifeRecord]:
        wages = wages or {}
        day_records: list[DailyLifeRecord] = []
        for character_id, health in self.world.health.items():
            profile = self.people.get(character_id, PersonProfile(character_id))
            active = [t for t in self.treatments.get(character_id, []) if t.active]
            treatment_cost = sum(t.daily_cost for t in active)
            available_money = self.world.money.get(character_id, 0.0)
            if treatment_cost > available_money:
                active = []
                treatment_cost = 0.0
            self.world.money[character_id] = max(0.0, available_money - treatment_cost)
            care_hours = sum(t.care_hours for t in active)
            profile.care_need = max(0.0, sum(c.severity for c in health.conditions) * 4.0 - care_hours)
            for condition in health.conditions:
                estimate = self.estimate_recovery(character_id, condition.condition_id)
                applicable = [t for t in active if t.condition_id == condition.condition_id]
                multiplier = 1.0 + sum(max(0.0, t.effectiveness) for t in applicable)
                # Sample within the estimated range. The outcome can be slower than expected.
                sampled = self.random.uniform(estimate.lower_bound, estimate.upper_bound)
                condition.severity = max(0.0, condition.severity - sampled * multiplier)
                condition.days_present += 1
            health.conditions = [c for c in health.conditions if c.severity > 0 or c.persistent]
            capacity = self._condition_capacity(health, "work")
            wage = max(0.0, float(wages.get(character_id, 0.0)))
            attended = capacity >= work_threshold and profile.alive
            earned = wage if attended else 0.0
            lost = wage - earned
            self.world.money[character_id] = self.world.money.get(character_id, 0.0) + earned
            self.world.stress[character_id] = max(0.0, min(1.0,
                self.world.stress.get(character_id, 0.0) + (0.04 if not attended else -0.015)
                + profile.care_need * 0.005))
            record = DailyLifeRecord(character_id, self.world.day, attended, earned, lost,
                                     profile.care_need, treatment_cost, capacity)
            self.daily_records.append(record)
            day_records.append(record)
        self.world.advance_day()
        return day_records

    def create_responsibility(self, obligation: SocialObligation) -> None:
        self.world.add_obligation(obligation)

    def provide_support(self, supporter_id: str, recipient_id: str, *,
                        money: float = 0.0, care_hours: float = 0.0) -> bool:
        if supporter_id == recipient_id or money < 0.0 or care_hours < 0.0:
            raise ValueError("support must be non-negative and between distinct people")
        available = self.world.money.get(supporter_id, 0.0)
        if available < money:
            return False
        self.world.money[supporter_id] = available - money
        self.world.money[recipient_id] = self.world.money.get(recipient_id, 0.0) + money
        key = self.world._trust_key(supporter_id, recipient_id)
        reverse = self.world._trust_key(recipient_id, supporter_id)
        tie = self.world.trust.get(key, 0.0)
        self.world.trust[key] = min(1.0, tie + 0.04 + min(0.02, care_hours * 0.005))
        self.world.trust[reverse] = min(1.0, self.world.trust.get(reverse, 0.0) + 0.02)
        self.world.stress[recipient_id] = max(0.0,
            self.world.stress.get(recipient_id, 0.0) - min(0.1, care_hours * 0.01))
        self.care_providers.setdefault(recipient_id, []).append(supporter_id)
        return True

    def resolve_after_death(self, deceased_id: str) -> list[ResponsibilityResolution]:
        profile = self.people.get(deceased_id)
        if profile:
            profile.alive = False
            profile.estate_money = max(0.0, self.world.money.get(deceased_id, 0.0))
        unresolved = [o for o in self.world.obligations
                      if not o.settled and not o.missed and o.debtor_id == deceased_id]
        outcomes: list[ResponsibilityResolution] = []
        for obligation in unresolved:
            amount = min(profile.estate_money if profile else 0.0, obligation.money_due)
            if amount > 0.0:
                if profile:
                    profile.estate_money -= amount
                obligation.settled = amount >= obligation.money_due
                self.world.money[obligation.creditor_id] = (
                    self.world.money.get(obligation.creditor_id, 0.0) + amount)
                result = ResponsibilityResolution(obligation.obligation_id,
                    ResponsibilityOutcome.PAID_FROM_ESTATE, None, amount, 0.02)
            else:
                candidates = []
                for person_id, person in self.people.items():
                    if person_id == deceased_id or not person.alive:
                        continue
                    trust = person.relationships.get(deceased_id, 0.0)
                    reciprocal = self.world.trust.get(self.world._trust_key(person_id, deceased_id), 0.0)
                    willingness = person.trait("compassion") * 0.45 + person.trait("duty") * 0.35
                    score = trust * 0.25 + reciprocal * 0.25 + willingness
                    candidates.append((score, person_id, person))
                candidates.sort(reverse=True, key=lambda row: row[0])
                if candidates and candidates[0][0] >= 0.55:
                    score, helper_id, helper = candidates[0]
                    available = self.world.money.get(helper_id, 0.0)
                    paid = min(available, obligation.money_due)
                    self.world.money[helper_id] = available - paid
                    self.world.money[obligation.creditor_id] = (
                        self.world.money.get(obligation.creditor_id, 0.0) + paid)
                    obligation.settled = paid >= obligation.money_due
                    result = ResponsibilityResolution(obligation.obligation_id,
                        ResponsibilityOutcome.ASSUMED_BY_SUPPORTER if obligation.settled
                        else ResponsibilityOutcome.UNRESOLVED, helper_id, paid, 0.05 if obligation.settled else -0.02)
                else:
                    result = ResponsibilityResolution(obligation.obligation_id,
                        ResponsibilityOutcome.UNRESOLVED, None, 0.0, -0.1)
            trust_key = self.world._trust_key(obligation.debtor_id, obligation.creditor_id)
            self.world.trust[trust_key] = max(-1.0, min(1.0,
                self.world.trust.get(trust_key, 0.0) + result.trust_change))
            self.resolutions.append(result)
            outcomes.append(result)
        return outcomes

    def schedule_ghost_window(self, window: GhostWindow) -> None:
        if window.start_hour < 0 or window.end_hour > 24 or window.start_hour >= window.end_hour:
            raise ValueError("ghost windows must fit within a day and have start < end")
        self.ghost_windows.append(window)

    def attempt_ghost_influence(self, npc_id: str, action: str, hour_of_day: float,
                                *, target_id: str | None = None) -> GhostDecision:
        life = self.world.life
        profile = self.people.get(npc_id)
        if life is None or life.state is not LifeState.GHOST:
            return GhostDecision(False, npc_id, action, "no active ghost", 0.0)
        window = next((w for w in self.ghost_windows
                       if w.start_hour <= hour_of_day < w.end_hour and action in w.permitted_actions), None)
        if window is None:
            return GhostDecision(False, npc_id, action, "outside permitted time/action window", 0.0)
        if profile is None:
            return GhostDecision(False, npc_id, action, "unknown NPC", 0.0)
        relationship = profile.relationships.get(life.character_id, 0.0)
        memory = profile.memories.get(life.character_id, 0.0)
        openness = profile.trait("spiritual_openness")
        fear = profile.trait("fearfulness")
        stubbornness = profile.trait("stubbornness")
        trust = self.world.trust.get(self.world._trust_key(npc_id, life.character_id), relationship)
        score = window.influence_strength * (0.25 * openness + 0.25 * fear
             + 0.25 * max(-1.0, min(1.0, trust)) + 0.25 * max(-1.0, min(1.0, memory)))
        score *= 1.0 - 0.65 * stubbornness
        score = max(0.0, min(1.0, score))
        # The NPC's own disposition and recollection decide whether to react.
        accepted = self.random.random() < score
        reason = "NPC accepted influence" if accepted else "NPC resisted based on personality and memories"
        decision = GhostDecision(accepted, npc_id, action, reason, score)
        self.ghost_action_log.append(decision)
        if accepted:
            profile.memories[life.character_id] = max(-1.0, min(1.0, memory + 0.03))
            if target_id:
                profile.memories[target_id] = max(-1.0, min(1.0, profile.memories.get(target_id, 0.0) + 0.01))
        return decision

    def snapshot(self) -> dict[str, Any]:
        """Compact, serializable diagnostics for save systems and regression tests."""
        return {
            "day": self.world.day,
            "people": {pid: {"alive": p.alive, "care_need": p.care_need,
                             "personality": dict(p.personality), "memories": dict(p.memories),
                             "relationships": dict(p.relationships)}
                       for pid, p in self.people.items()},
            "daily_records": [r.__dict__.copy() for r in self.daily_records],
            "resolutions": [{"obligation_id": r.obligation_id, "outcome": r.outcome.value,
                             "responsible_person": r.responsible_person, "amount_paid": r.amount_paid,
                             "trust_change": r.trust_change} for r in self.resolutions],
        }
