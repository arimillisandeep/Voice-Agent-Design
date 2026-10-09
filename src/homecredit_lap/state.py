"""Internal state for the LAP pre-qualification call.

Mirrors `config/state_schema.yaml` and the `submit_eligibility_facts` tool payload.
Nothing in here is ever spoken to the customer.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class StrEnum(str, Enum):
    """str-Enum so JSON serialisation and == comparisons against raw strings work."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class PropertyType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"
    INDUSTRIAL = "industrial"
    AGRICULTURAL = "agricultural"
    OTHER = "other"
    NONE = "none"          # customer owns no property


class Ownership(StrEnum):
    SOLE = "sole"
    JOINT = "joint"


class YesNo(StrEnum):
    YES = "yes"
    NO = "no"


class Occupation(StrEnum):
    SALARIED = "salaried"
    SELF_EMPLOYED = "self_employed"
    NONE = "none"          # unemployed / student / retired without income


class IncomeMode(StrEnum):
    BANK = "bank"
    CASH = "cash"
    MIXED = "mixed"        # partly cash -> needs one clarification, then resolves


class Terminal(StrEnum):
    NONE = ""
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    TRANSFER = "transfer"
    CALLBACK = "callback"
    DECLINED = "declined"
    DNC = "do_not_call"
    WRONG_PERSON = "wrong_person"
    ABANDONED = "abandoned"


# --------------------------------------------------------------------------- #
# Numeric limits. Defined here (not in rules.py) so CallState can apply the
# amount-cap normalisation without importing the rules module.
# --------------------------------------------------------------------------- #
MAX_LOAN_AMOUNT = 75_00_000      # ₹75,00,000
MIN_TENURE_YEARS = 3
MAX_TENURE_YEARS = 15

# The 7 checklist items, in the order the agent must ask them.
CHECKLIST_ORDER: tuple[str, ...] = (
    "property_type",
    "ownership_status",
    "documents_original",
    "loan_amount",
    "occupation",
    "income_mode",
    "market_value",
    "tenure_years",
)
# `occupation` + `income_mode` are checklist item 5 (two facts, one item).
CHECKLIST_ITEMS: tuple[str, ...] = (
    "property_type",
    "ownership_status",
    "documents_original",
    "loan_amount",
    "occupation_and_income",
    "market_value",
    "tenure_years",
)


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
@dataclass
class CallState:
    # --- identity / routing -------------------------------------------------
    customer_verified: Optional[bool] = None
    wrong_person: bool = False

    # --- the 7 eligibility facts -------------------------------------------
    property_type: Optional[str] = None
    ownership_status: Optional[str] = None
    documents_original: Optional[str] = None      # yes | no
    loan_amount: Optional[int] = None             # rupees
    occupation: Optional[str] = None
    income_mode: Optional[str] = None
    market_value: Optional[int] = None            # rupees
    tenure_years: Optional[float] = None

    # --- amount-cap negotiation (§9 of the prompt) -------------------------
    cap_offer_pending: bool = False               # asked >75L, offered the cap
    cap_offer_accepted: Optional[bool] = None

    # --- competing-product / transfer routing ------------------------------
    existing_property_loan: Optional[bool] = None
    emi_reduction_request: Optional[bool] = None

    # --- non-qualification terminals ---------------------------------------
    busy: bool = False
    callback_time: Optional[str] = None
    declined: bool = False
    do_not_call: bool = False
    requested_human: bool = False
    ended_by_customer: bool = False

    # --- outcome ------------------------------------------------------------
    terminal: str = Terminal.NONE.value
    terminal_reason: Optional[str] = None
    handoff_completed: bool = False

    # --- raw audit trail ----------------------------------------------------
    facts_log: list[dict[str, Any]] = field(default_factory=list)
    clarifications_pending: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    def record(self, key: str, value: Any, source: str = "customer") -> bool:
        """Record one fact. Returns True if the value actually changed.

        Corrections overwrite: the latest clear answer always wins (§6.1).
        """
        if key not in _RECORDABLE:
            raise KeyError(f"unknown fact key: {key!r}")
        if value is None:
            return False
        old = getattr(self, key)
        if old == value:
            changed = False
        else:
            setattr(self, key, value)
            self.facts_log.append({"key": key, "old": old, "new": value, "source": source})
            changed = True

        # Accepting the ₹75 lakh cap rewrites the requested amount to the cap, so the
        # request never reaches the CRM as an out-of-policy figure (§9).
        if key == "cap_offer_accepted" and value is True:
            if self.loan_amount is None or self.loan_amount > MAX_LOAN_AMOUNT:
                prev = self.loan_amount
                self.loan_amount = MAX_LOAN_AMOUNT
                self.facts_log.append({"key": "loan_amount", "old": prev,
                                       "new": MAX_LOAN_AMOUNT, "source": "cap_accepted"})
                changed = True
            self.cap_offer_pending = False
        elif key == "loan_amount" and value is not None and value > MAX_LOAN_AMOUNT:
            self.cap_offer_pending = True

        return changed

    def record_many(self, facts: dict[str, Any], source: str = "customer") -> list[str]:
        return [k for k, v in facts.items() if self.record(k, v, source)]

    # ------------------------------------------------------------------ #
    def answered(self, key: str) -> bool:
        if key == "occupation_and_income":
            return self.occupation is not None and self.income_mode in ("bank", "cash")
        return getattr(self, key, None) is not None

    def missing_items(self) -> list[str]:
        """Checklist items with no answer yet, in ask order."""
        return [item for item in CHECKLIST_ITEMS if not self.answered(item)]

    def all_items_answered(self) -> bool:
        return not self.missing_items()

    def first_missing(self) -> Optional[str]:
        missing = self.missing_items()
        return missing[0] if missing else None

    def facts_payload(self) -> dict[str, Any]:
        return {
            "property_type": self.property_type,
            "ownership_status": self.ownership_status,
            "documents_original": self.documents_original,
            "loan_amount": self.loan_amount,
            "occupation": self.occupation,
            "income_mode": self.income_mode,
            "market_value": self.market_value,
            "tenure_years": self.tenure_years,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RECORDABLE: frozenset[str] = frozenset(
    {
        "customer_verified",
        "wrong_person",
        "property_type",
        "ownership_status",
        "documents_original",
        "loan_amount",
        "occupation",
        "income_mode",
        "market_value",
        "tenure_years",
        "cap_offer_accepted",
        "existing_property_loan",
        "emi_reduction_request",
        "busy",
        "callback_time",
        "declined",
        "do_not_call",
        "requested_human",
        "ended_by_customer",
    }
)
