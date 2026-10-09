"""Deterministic eligibility engine.

Every number/threshold rule from the master prompt lives here, in code, so the LLM
never has to do arithmetic or remember a threshold. The agent calls
`submit_eligibility_facts` and simply speaks the `say` text this module returns.

Design contract
---------------
* Pure functions, no I/O, no randomness -> unit-testable and replayable.
* `decide()` is total: it always returns a Decision, never raises.
* Disqualification is checked BEFORE completeness, so a disqualifying fact stops the
  call even when it arrives bundled with 4 other answers (master prompt §54/§53).
* Routing terminals (wrong person, transfer, busy, decline) outrank eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .state import (MAX_LOAN_AMOUNT, MAX_TENURE_YEARS, MIN_TENURE_YEARS, CallState,
                    IncomeMode, Occupation, PropertyType, Terminal)

# --------------------------------------------------------------------------- #
# Business configuration (single source of truth = config/product_rules.yaml)
# --------------------------------------------------------------------------- #
ELIGIBLE_PROPERTY_TYPES = frozenset(
    {PropertyType.RESIDENTIAL.value, PropertyType.COMMERCIAL.value, PropertyType.INDUSTRIAL.value}
)
ELIGIBLE_OCCUPATIONS = frozenset(
    {Occupation.SALARIED.value, Occupation.SELF_EMPLOYED.value}
)

# Spoken closing lines (en-IN). Localisation: see prompt/languages/*.md
# The question spoken for each checklist item. `evaluate` returns this as `say` so the
# runtime always has something to speak on a `continue` action (the LLM is still free to
# rephrase naturally in the target language).
ASK = {
    "property_type": "What type of property do you have?",
    "ownership_status": "Is the property solely in your name, or is it jointly owned?",
    "documents_original": "Do you have the original property documents available for verification?",
    "loan_amount": "Approximately how much are you looking to borrow?",
    "occupation_and_income": "And what do you do for work — and does that income come into your "
                             "bank account?",
    "occupation": "What do you do for work?",
    "income_mode": "Is your income received through your bank account, or in cash?",
    "market_value": "Approximately what is the current market value of the property?",
    "tenure_years": "How many years would you like to take to repay the loan?",
    "callback_time": "Of course — when would be a convenient time to call you back?",
}


def ask_for(item: Optional[str]) -> Optional[str]:
    """The question line for a checklist item, or None when the item is unknown."""
    return ASK.get(item) if item else None


SAY = {
    "qualified": (
        "Thank you for those details. Based on this preliminary check you meet the criteria "
        "for the next stage. A senior loan expert will call you shortly with the exact interest "
        "rate and the next steps."
    ),
    "agricultural": (
        "I see. Unfortunately agricultural property isn't covered by this offer. "
        "Thank you for your time."
    ),
    "no_property": (
        "I see — this offer is only against a property you already own, so we won't be able to "
        "take this forward. Thank you for your time."
    ),
    "other_property": (
        "Thank you. That type of property isn't covered by this offer. Thank you for your time."
    ),
    "documents": (
        "Thank you for clarifying. Original property documents are needed for this offer, so we "
        "can't take it further right now. Thank you for your time."
    ),
    "cash_income": (
        "Thank you for clarifying. Income received in cash doesn't meet this offer's criteria. "
        "Thank you for your time."
    ),
    "tenure_short": (
        "Thank you — the repayment period for this offer is between 3 and 15 years, so we can't "
        "proceed on that basis. Thank you for your time."
    ),
    "tenure_long": (
        "Thank you — the repayment period for this offer is between 3 and 15 years, so we can't "
        "proceed on that basis. Thank you for your time."
    ),
    "amount_above_cap_refused": (
        "I understand. This offer is limited to 75 lakh rupees, so I won't be able to take this "
        "further. Thank you for your time."
    ),
    "occupation_none": (
        "Thank you for letting me know. This offer needs a regular income source, so we won't be "
        "able to take it forward. Thank you for your time."
    ),
    "transfer": (
        "Thank you for clarifying. Since this involves an existing loan, our loan-transfer "
        "specialist will handle it and will contact you shortly. Thank you for your time."
    ),
    "callback": "Thank you — we'll call you back then. Have a good day.",
    "declined": "I understand. Thank you for your time. Have a good day.",
    "dnc": "I'm sorry for the disturbance. I've noted your request and you won't be called again. "
           "Have a good day.",
    "wrong_person": (
        "I'm sorry, I was trying to reach {customer_name}. I'll call back later. Thank you."
    ),
    "amount_above_cap_offer": (
        "This offer is available for up to 75 lakh rupees. Would you like to proceed with "
        "75 lakh as the amount?"
    ),
}


ACTION_CONTINUE = "continue"          # ask next_item
ACTION_CLARIFY = "clarify"            # ask a clarification for next_item
ACTION_OFFER_CAP = "offer_cap"        # master prompt 9 negotiation turn
ACTION_SUBMIT = "submit"              # hand off to senior loan expert
ACTION_TRANSFER = "transfer"          # loan-transfer specialist
ACTION_CALLBACK = "schedule_callback"
ACTION_END = "end_call"


@dataclass
class Decision:
    """What the agent must do next."""

    action: str                      # see ACTION_* below
    terminal: str = Terminal.NONE.value
    reason: Optional[str] = None
    say: Optional[str] = None        # exact line to speak (translate to target language)
    say_key: Optional[str] = None
    next_item: Optional[str] = None  # checklist key to ask next
    lead_status: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def ends_call(self) -> bool:
        """True when the call is over after this turn.

        `submit` is deliberately excluded: it is the instruction to call
        submit_eligibility_facts, and the handoff only completes when that tool runs.
        """
        return self.terminal != Terminal.NONE.value and self.action != ACTION_SUBMIT


# --------------------------------------------------------------------------- #
# Disqualification checks
# --------------------------------------------------------------------------- #
def _disqualifier(state: CallState) -> Optional[tuple[str, str]]:
    """Return (reason, say_key) for the first hard failure, else None.

    Order matters only for which reason is spoken; any one of these ends the call.
    """
    # 1. Amount cap refused (checked first: it is an explicit customer decision)
    if (
        state.loan_amount is not None
        and state.loan_amount > MAX_LOAN_AMOUNT
        and state.cap_offer_accepted is False
    ):
        return "loan_amount_above_cap_refused", "amount_above_cap_refused"

    # 2. Property type
    if state.property_type == PropertyType.AGRICULTURAL.value:
        return "agricultural_property", "agricultural"
    if state.property_type == PropertyType.NONE.value:
        return "no_property_owned", "no_property"
    if state.property_type == PropertyType.OTHER.value:
        return "ineligible_property_type", "other_property"

    # 3. Original documents
    if state.documents_original == "no":
        return "original_documents_unavailable", "documents"

    # 4. Income mode
    if state.income_mode == IncomeMode.CASH.value:
        return "cash_income", "cash_income"

    # 5. Occupation
    if state.occupation == Occupation.NONE.value:
        return "no_income_source", "occupation_none"

    # 6. Tenure window
    if state.tenure_years is not None:
        if state.tenure_years < MIN_TENURE_YEARS:
            return "tenure_below_minimum", "tenure_short"
        if state.tenure_years > MAX_TENURE_YEARS:
            return "tenure_above_maximum", "tenure_long"

    return None


def _needs_clarification(state: CallState) -> Optional[tuple[str, str]]:
    """Facts that are recorded but still ambiguous -> one clarifying question."""
    if state.income_mode == IncomeMode.MIXED.value:
        return "income_mode", (
            "Understood. Would you say most of your income comes into your bank account, "
            "or is it mostly in cash?"
        )
    if state.ownership_status == "unclear":
        return "ownership_status", (
            "Just to confirm — is the property in your name alone, or jointly with someone?"
        )
    if state.documents_original == "unclear":
        return "documents_original", (
            "Just to confirm — are the original property documents available for verification?"
        )
    if state.property_type == "unclear":
        return "property_type", "Could you tell me what kind of property it is?"
    if state.loan_amount == 0:
        return "loan_amount", "Roughly how much were you looking to borrow?"
    return None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def evaluate(state: CallState, customer_name: str = "the customer") -> Decision:
    """Full routing decision for the current turn. Mirrors master prompt §5."""

    # ---- Priority 1: customer ends the call / DNC -------------------------
    if state.do_not_call:
        return Decision(ACTION_END, Terminal.DNC.value, "do_not_call", say=SAY["dnc"],
                        say_key="dnc", lead_status="dnc")
    if state.ended_by_customer:
        return Decision(ACTION_END, Terminal.DECLINED.value, "customer_ended_call",
                        say=SAY["declined"], say_key="declined", lead_status="closed_lost")

    # ---- Priority 2: wrong person ----------------------------------------
    if state.wrong_person or state.customer_verified is False:
        line = SAY["wrong_person"].format(customer_name=customer_name)
        return Decision(ACTION_END, Terminal.WRONG_PERSON.value, "wrong_person", say=line,
                        say_key="wrong_person", lead_status="wrong_person")

    # ---- Priority 3: existing loan / EMI reduction -> transfer ------------
    if state.existing_property_loan or state.emi_reduction_request:
        return Decision(
            ACTION_TRANSFER, Terminal.TRANSFER.value, "existing_loan_or_emi_reduction",
            say=SAY["transfer"], say_key="transfer", lead_status="transferred_loan_transfer",
            payload={"specialist": "loan_transfer"},
        )

    # ---- Priority 4: busy -> callback ------------------------------------
    if state.busy:
        if not state.callback_time:
            return Decision(ACTION_CONTINUE, reason="callback_time_required",
                            say=ASK["callback_time"], next_item="callback_time")
        return Decision(ACTION_CALLBACK, Terminal.CALLBACK.value, "customer_busy",
                        say=SAY["callback"], say_key="callback", lead_status="callback_scheduled",
                        payload={"callback_time": state.callback_time})

    # ---- Priority 5: declines -------------------------------------------
    if state.declined:
        return Decision(ACTION_END, Terminal.DECLINED.value, "customer_declined",
                        say=SAY["declined"], say_key="declined", lead_status="closed_lost")

    # ---- Priority 6: hard disqualification ------------------------------
    dq = _disqualifier(state)
    if dq:
        reason, key = dq
        return Decision(ACTION_END, Terminal.DISQUALIFIED.value, reason, say=SAY[key],
                        say_key=key, lead_status="disqualified",
                        payload={"disqualification_reason": reason})

    # ---- Priority 6b: amount above cap, not yet resolved -> offer the cap --
    if (
        state.loan_amount is not None
        and state.loan_amount > MAX_LOAN_AMOUNT
        and state.cap_offer_accepted is None
    ):
        return Decision(ACTION_OFFER_CAP, reason="loan_amount_above_cap",
                        say=SAY["amount_above_cap_offer"], say_key="amount_above_cap_offer",
                        next_item="loan_amount",
                        payload={"requested_amount": state.loan_amount,
                                 "cap": MAX_LOAN_AMOUNT})

    # ---- Priority 6c: ambiguous fact -> one clarification -----------------
    clar = _needs_clarification(state)
    if clar:
        item, line = clar
        return Decision(ACTION_CLARIFY, reason=f"ambiguous_{item}", say=line, next_item=item)

    # ---- Priority 7: complete -> submit ----------------------------------
    if state.all_items_answered():
        return Decision(
            ACTION_SUBMIT, Terminal.QUALIFIED.value, "all_criteria_passed",
            say=SAY["qualified"], say_key="qualified", lead_status="qualified_handoff",
            next_item=None, payload=state.facts_payload(),
        )

    # ---- Priority 8/9: ask the first missing checklist item --------------
    item = state.first_missing()
    return Decision(ACTION_CONTINUE, reason="collecting", next_item=item, say=ask_for(item))


def decide(state: CallState, customer_name: str = "the customer") -> Decision:
    """Alias kept for tool-layer readability."""
    return evaluate(state, customer_name)


def next_question_key(state: CallState) -> Optional[str]:
    """Convenience helper for the tool layer / prompt debugging."""
    return evaluate(state).next_item


def gate_report(state: CallState) -> dict[str, Any]:
    """Human-readable audit of the final handoff gate (§46 of the original prompt)."""
    checks = {
        "property_type_eligible": state.property_type in ELIGIBLE_PROPERTY_TYPES,
        "ownership_captured": state.ownership_status in ("sole", "joint"),
        "documents_original": state.documents_original == "yes",
        "loan_amount_within_cap": (
            state.loan_amount is not None and state.loan_amount <= MAX_LOAN_AMOUNT
        ),
        "occupation_eligible": state.occupation in ELIGIBLE_OCCUPATIONS,
        "income_mode_bank": state.income_mode == IncomeMode.BANK.value,
        "market_value_captured": state.market_value is not None,
        "tenure_within_window": (
            state.tenure_years is not None
            and MIN_TENURE_YEARS <= state.tenure_years <= MAX_TENURE_YEARS
        ),
        "no_transfer_required": not (state.existing_property_loan or state.emi_reduction_request),
        "not_disqualified": _disqualifier(state) is None,
    }
    return {"passed": all(checks.values()), "checks": checks}
