"""Replay-safe investigator questions and witness responses."""
from __future__ import annotations
from dataclasses import dataclass
import json
import math
from .testimony import TestimonyDetail, TestimonyRecord

@dataclass(frozen=True)
class TestimonyInquiry:
    inquiry_id: str
    event_id: str
    witness_id: str
    attribute_key: str
    asked_tick: int

@dataclass(frozen=True)
class TestimonyResponse:
    inquiry_id: str
    answered_tick: int
    answered: bool
    value: str | int | float | bool | None
    confidence: float

    def __post_init__(self):
        if not self.inquiry_id:
            raise ValueError("inquiry_id must be non-empty")
        if isinstance(self.answered_tick, bool) or not isinstance(self.answered_tick, int) or self.answered_tick < 0:
            raise ValueError("answered_tick must be a non-negative integer")
        if not isinstance(self.answered, bool):
            raise ValueError("answered must be bool")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)) or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite and in [0, 1]")
        if not self.answered and self.value is not None:
            raise ValueError("a refusal or no-answer response cannot contain a value")

class TestimonyInquiryLedger:
    """Append-only questions/responses; duplicate identical events are safe."""
    SCHEMA_VERSION = 1
    def __init__(self, inquiries=(), responses=()):
        self._inquiries = {}
        self._responses = {}
        for item in inquiries:
            self.append_inquiry(item)
        for item in responses:
            self.append_response(item)

    def append_inquiry(self, inquiry: TestimonyInquiry):
        if not isinstance(inquiry, TestimonyInquiry):
            raise TypeError("inquiry must be TestimonyInquiry")
        if not all(isinstance(v, str) and v.strip() for v in
                   (inquiry.inquiry_id, inquiry.event_id, inquiry.witness_id, inquiry.attribute_key)):
            raise ValueError("inquiry identifiers and attribute must be non-empty")
        if isinstance(inquiry.asked_tick, bool) or not isinstance(inquiry.asked_tick, int) or inquiry.asked_tick < 0:
            raise ValueError("asked_tick must be a non-negative integer")
        old = self._inquiries.get(inquiry.inquiry_id)
        if old is not None and old != inquiry:
            raise ValueError("inquiry ID reused with different content")
        self._inquiries.setdefault(inquiry.inquiry_id, inquiry)
        return self._inquiries[inquiry.inquiry_id]

    def append_response(self, response: TestimonyResponse):
        if not isinstance(response, TestimonyResponse):
            raise TypeError("response must be TestimonyResponse")
        inquiry = self._inquiries.get(response.inquiry_id)
        if inquiry is None:
            raise KeyError(response.inquiry_id)
        if response.answered_tick < inquiry.asked_tick:
            raise ValueError("response cannot precede inquiry")
        old = self._responses.get(response.inquiry_id)
        if old is not None and old != response:
            raise ValueError("inquiry response cannot be rewritten")
        self._responses.setdefault(response.inquiry_id, response)
        return self._responses[response.inquiry_id]

    def get_inquiry(self, inquiry_id):
        return self._inquiries[inquiry_id]

    def get_response(self, inquiry_id):
        return self._responses[inquiry_id]

    def inquiries(self):
        return tuple(self._inquiries[k] for k in sorted(self._inquiries))

    def responses(self):
        return tuple(self._responses[k] for k in sorted(self._responses))

    def to_testimony_record(self, inquiry_id: str, testimony_id: str, recorded_hour: float,
                            *, decay_rate_per_hour: float = 0.01) -> TestimonyRecord | None:
        """Materialize an answered inquiry as a normal testimony record."""
        inquiry = self._inquiries[inquiry_id]
        response = self._responses.get(inquiry_id)
        if response is None or not response.answered:
            return None
        if not isinstance(recorded_hour, (int, float)) or isinstance(recorded_hour, bool) or not math.isfinite(recorded_hour) or recorded_hour < 0:
            raise ValueError("recorded_hour must be finite and non-negative")
        detail = TestimonyDetail(f"inquiry:{inquiry_id}", inquiry.attribute_key,
                                 response.value, float(response.confidence))
        return TestimonyRecord(testimony_id, inquiry.event_id, inquiry.witness_id,
            inquiry.asked_tick, float(recorded_hour), float(decay_rate_per_hour),
            (detail,), ())

    def to_json(self):
        payload = {"schema_version": self.SCHEMA_VERSION,
            "inquiries": [{"inquiry_id": x.inquiry_id, "event_id": x.event_id,
                "witness_id": x.witness_id, "attribute_key": x.attribute_key,
                "asked_tick": x.asked_tick} for x in self.inquiries()],
            "responses": [{"inquiry_id": x.inquiry_id, "answered_tick": x.answered_tick,
                "answered": x.answered, "value": x.value, "confidence": x.confidence}
                for x in self.responses()]}
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload):
        try:
            raw = json.loads(payload)
            if raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported inquiry schema")
            inquiries = tuple(TestimonyInquiry(**x) for x in raw["inquiries"])
            responses = tuple(TestimonyResponse(**x) for x in raw["responses"])
            return cls(inquiries, responses)
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid testimony inquiry snapshot") from exc
