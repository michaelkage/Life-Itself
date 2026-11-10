"""Explicit, context-sensitive activation of NPC learned associations.

Trigger definitions are authored per NPC. Runtime observations supply literal
cue and context tags; this module does not infer sensory input, identity, danger,
or intent. A trigger only activates when its required context is present and
excluded context is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .psychological_conditioning import NPCConditioningLedger, ConditionedResponse


def _token(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _tokens(values, name):
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{name} must be an iterable of strings, not a string")
    result = tuple(sorted({_token(value, name) for value in values}))
    return result


@dataclass(frozen=True)
class PsychologicalTrigger:
    trigger_id: str
    owner_id: str
    cue: str
    aliases: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    excluded_context: tuple[str, ...] = ()

    def __post_init__(self):
        _token(self.trigger_id, "trigger_id")
        _token(self.owner_id, "owner_id")
        _token(self.cue, "cue")
        object.__setattr__(self, "aliases", _tokens(self.aliases, "alias"))
        object.__setattr__(self, "required_context", _tokens(self.required_context, "required_context"))
        object.__setattr__(self, "excluded_context", _tokens(self.excluded_context, "excluded_context"))
        if set(self.required_context) & set(self.excluded_context):
            raise ValueError("context cannot be both required and excluded")


@dataclass(frozen=True)
class TriggerActivation:
    trigger_id: str
    owner_id: str
    matched_cue: str
    matched_context: tuple[str, ...]
    response: ConditionedResponse


class PsychologicalTriggerAdapter:
    """Evaluate explicit observations against an NPC's authored trigger set."""

    @staticmethod
    def evaluate(
        ledger: NPCConditioningLedger,
        owner_id: str,
        observed_cues: Iterable[str],
        context: Iterable[str],
        triggers: Iterable[PsychologicalTrigger],
    ) -> tuple[TriggerActivation, ...]:
        if not isinstance(ledger, NPCConditioningLedger):
            raise TypeError("ledger must be an NPCConditioningLedger")
        owner_id = _token(owner_id, "owner_id")
        cues = set(_tokens(observed_cues, "observed cue"))
        context_set = set(_tokens(context, "context"))
        if isinstance(triggers, (str, bytes)):
            raise TypeError("triggers must be an iterable of PsychologicalTrigger")
        definitions = tuple(triggers)
        seen = set()
        activations = []
        for trigger in sorted(definitions, key=lambda item: item.trigger_id):
            if not isinstance(trigger, PsychologicalTrigger):
                raise TypeError("triggers must contain PsychologicalTrigger values")
            if trigger.owner_id != owner_id:
                continue
            if trigger.trigger_id in seen:
                raise ValueError("duplicate trigger_id for one evaluation")
            seen.add(trigger.trigger_id)
            cue_options = {trigger.cue, *trigger.aliases}
            matched = sorted(cues & cue_options)
            if not matched:
                continue
            if not set(trigger.required_context).issubset(context_set):
                continue
            if set(trigger.excluded_context) & context_set:
                continue
            response = ledger.assess(owner_id, trigger.cue)
            activations.append(TriggerActivation(
                trigger.trigger_id, owner_id, matched[0],
                tuple(sorted(set(trigger.required_context) & context_set)), response,
            ))
        return tuple(activations)
