"""Home Credit LAP outbound voice agent — deterministic rule engine."""

from __future__ import annotations

from .parsing import (classify_utterance, detect_intents, extract_facts, parse_amount,
                      parse_documents, parse_income_mode, parse_occupation, parse_ownership,
                      parse_property_type, parse_tenure_years)
from .rules import (ACTION_CLARIFY, ACTION_CONTINUE, ACTION_END, ACTION_OFFER_CAP,
                    ACTION_SUBMIT, ACTION_TRANSFER, MAX_LOAN_AMOUNT, MAX_TENURE_YEARS,
                    MIN_TENURE_YEARS, Decision, decide, evaluate, gate_report)
from .state import CHECKLIST_ITEMS, CHECKLIST_ORDER, CallState
from .tools import LapAgentTools

__version__ = "2.0.0"

__all__ = [
    "CallState",
    "CHECKLIST_ITEMS",
    "CHECKLIST_ORDER",
    "LapAgentTools",
    "Decision",
    "evaluate",
    "decide",
    "gate_report",
    "MAX_LOAN_AMOUNT",
    "MIN_TENURE_YEARS",
    "MAX_TENURE_YEARS",
    "ACTION_CONTINUE",
    "ACTION_CLARIFY",
    "ACTION_OFFER_CAP",
    "ACTION_SUBMIT",
    "ACTION_TRANSFER",
    "ACTION_END",
    "extract_facts",
    "detect_intents",
    "classify_utterance",
    "parse_amount",
    "parse_tenure_years",
    "parse_property_type",
    "parse_ownership",
    "parse_documents",
    "parse_occupation",
    "parse_income_mode",
    "__version__",
]
