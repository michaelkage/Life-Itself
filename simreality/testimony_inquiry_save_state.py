"""Canonical save-state wrapper for investigator inquiry history."""
from __future__ import annotations

from dataclasses import dataclass
import json

from .testimony_inquiries import TestimonyInquiryLedger


@dataclass(frozen=True)
class TestimonyInquirySnapshot:
    ledger_json: str

    SCHEMA_VERSION = 1

    def __post_init__(self):
        restored = TestimonyInquiryLedger.from_json(self.ledger_json)
        if restored.to_json() != self.ledger_json:
            raise ValueError("inquiry ledger must use canonical JSON")

    @classmethod
    def capture(cls, ledger: TestimonyInquiryLedger) -> "TestimonyInquirySnapshot":
        if not isinstance(ledger, TestimonyInquiryLedger):
            raise TypeError("ledger must be a TestimonyInquiryLedger")
        return cls(ledger.to_json())

    def to_json(self) -> str:
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "ledger": json.loads(self.ledger_json),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    @classmethod
    def from_json(cls, payload: str) -> "TestimonyInquirySnapshot":
        try:
            raw = json.loads(payload)
            if not isinstance(raw, dict) or raw.get("schema_version") != cls.SCHEMA_VERSION:
                raise ValueError("unsupported testimony inquiry snapshot schema")
            ledger_json = json.dumps(raw["ledger"], sort_keys=True, separators=(",", ":"), allow_nan=False)
            result = cls(ledger_json)
            if result.to_json() != payload:
                raise ValueError("testimony inquiry snapshot must use canonical JSON")
            return result
        except ValueError:
            raise
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("invalid testimony inquiry snapshot") from exc

    def restore(self) -> TestimonyInquiryLedger:
        return TestimonyInquiryLedger.from_json(self.ledger_json)
