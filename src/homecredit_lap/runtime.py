"""Call runtime: wires utterance parsing -> state -> deterministic rules -> next action.

This is the module a Retell/Vapi webhook calls. The LLM never evaluates a threshold;
it reports what it heard and this module tells it what to say next.

Two entry points:

* :func:`process_turn` — one customer utterance in, one instruction out.
* :class:`CallSession`  — a stateful wrapper holding a whole call, with `handle()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .parsing import classify_utterance, extract_facts, parse_callback_time
from .rules import (ACTION_CLARIFY, ACTION_CONTINUE, ACTION_END, ACTION_OFFER_CAP,
                    ACTION_SUBMIT, ACTION_TRANSFER, Decision, evaluate)
from .state import CallState

# Intent -> state flag. First matching rule wins, mirroring prompt §5 priority.
_INTENT_TO_STATE: dict[str, tuple[str, Any]] = {
    "dnc": ("do_not_call", True),
    "end_call": ("ended_by_customer", True),
    "wrong_person": ("wrong_person", True),
    "existing_loan": ("existing_property_loan", True),
    "emi_reduction": ("emi_reduction_request", True),
    "transfer": ("existing_property_loan", True),
    "busy": ("busy", True),
    "decline": ("declined", True),
}

# Intents that must be checked in priority order regardless of dict order.
_INTENT_PRIORITY = (
    "dnc", "end_call", "wrong_person", "existing_loan", "emi_reduction",
    "transfer", "busy", "decline",
)

# How many times the agent may re-ask one checklist item before moving on (§6.1).
MAX_REASKS = 2

ASK_FALLBACK = "Could you tell me a little more about the {item}?"

CLARIFY_BY_ITEM = {
    # Composite item 5: asked as one natural breath, but satisfied only when BOTH the
    # occupation and a resolved (bank|cash) income mode are known.
    "occupation_and_income": "And what do you do for work — and does that income come into "
                             "your bank account?",
    "income_mode": "Understood. Would you say most of your income comes into your bank "
                   "account, or is it mostly in cash?",
    "ownership_status": "Just to confirm — is the property in your name alone, or jointly "
                        "with someone?",
    "documents_original": "Just to confirm — are the original property documents available "
                          "for verification?",
    "property_type": "Could you tell me what kind of property it is?",
    "loan_amount": "Roughly how much were you looking to borrow?",
    "market_value": "Could you give me an approximate current market value?",
    "tenure_years": "And how many years would you like to take to repay it?",
    "occupation": "And what do you do for work?",
}


@dataclass
class TurnResult:
    """Everything the platform needs to act on one turn."""

    say: Optional[str]
    action: str
    end_call: bool = False
    terminal: str = ""
    reason: Optional[str] = None
    next_item: Optional[str] = None
    missing_items: list[str] = field(default_factory=list)
    lead_status: Optional[str] = None
    intents: list[str] = field(default_factory=list)
    recorded: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def as_tool_result(self) -> dict[str, Any]:
        return {
            "say": self.say,
            "action": self.action,
            "end_call": self.end_call,
            "terminal": self.terminal or None,
            "reason": self.reason,
            "next_item": self.next_item,
            "missing_items": self.missing_items,
            "lead_status": self.lead_status,
            "intents": self.intents,
            "recorded": self.recorded,
            **self.payload,
        }


def _apply_intents(state: CallState, intents: list[str]) -> None:
    for name in _INTENT_PRIORITY:
        if name in intents:
            key, value = _INTENT_TO_STATE[name]
            state.record(key, value, source=f"intent:{name}")


def process_turn(state: CallState, utterance: str, *,
                 customer_name: str = "the customer",
                 facts: Optional[dict[str, Any]] = None,
                 reask_counts: Optional[dict[str, int]] = None) -> TurnResult:
    """Apply one customer utterance to the call state and return what to do next.

    `facts` lets the LLM (or a test) pass pre-normalised values instead of relying on
    the regex extractor — that is the production path. `reask_counts` is mutated so the
    caller can enforce the two-attempt limit per checklist item.
    """
    reasks = reask_counts if reask_counts is not None else {}
    parsed = classify_utterance(utterance) if utterance else {"intents": [], "facts": {}}
    intents: list[str] = parsed["intents"]

    # Facts from the LLM take precedence over regex extraction.
    extracted: dict[str, Any] = dict(parsed["facts"])
    if facts:
        extracted.update(facts)

    # While a callback time is outstanding the turn is an answer to that question, so a
    # bare number ("tomorrow around 11") must become a time, never a rupee amount.
    awaiting_callback = (state.busy or "busy" in intents) and not state.callback_time
    if awaiting_callback and "callback_time" not in extracted:
        cb = parse_callback_time(utterance)
        if cb:
            extracted["callback_time"] = cb
            extracted.pop("loan_amount", None)
            extracted.pop("market_value", None)
        elif not facts:
            # Ambiguous ("later", "some time") -> do not record a guessed amount either.
            extracted.pop("loan_amount", None)
            extracted.pop("market_value", None)

    _apply_intents(state, intents)
    changed = state.record_many(extracted, source="utterance")

    decision: Decision = evaluate(state, customer_name)

    # Busy with no callback time yet -> ask for it (not a checklist question).
    if decision.next_item == "callback_time" and not state.callback_time:
        reasks["callback_time"] = reasks.get("callback_time", 0) + 1

    # Two-attempt limit: stop interrogating an item the customer will not answer.
    #
    # The counter only advances on a turn that produced NO new facts. If the customer is
    # answering other questions productively, a still-missing item is not "unanswered
    # twice" -- counting it would abandon an otherwise good call (a customer who bundles
    # answers out of order legitimately leaves one item pending across several turns).
    item = decision.next_item
    stalled = not changed and not intents
    if (decision.action in (ACTION_CONTINUE, ACTION_CLARIFY) and item
            and item in CLARIFY_BY_ITEM and stalled):
        reasks[item] = reasks.get(item, 0) + 1
        if reasks[item] > MAX_REASKS:
            state.clarifications_pending.append(item)
            # Skip past this item by asking the next one that is still unanswered.
            remaining = [i for i in state.missing_items()
                         if i != item and reasks.get(i, 0) < MAX_REASKS]
            # A fallback line keeps a live call alive if an item is ever added to the
            # checklist without a matching prompt -- a KeyError here would drop the call.
            if remaining:
                nxt = remaining[0]
                decision = Decision(decision.action, decision.terminal, decision.reason,
                                    say=CLARIFY_BY_ITEM.get(nxt, ASK_FALLBACK.format(item=nxt)),
                                    next_item=nxt)
            else:
                decision = Decision(ACTION_END, "abandoned", "customer_unresponsive",
                                    say="I don't want to take any more of your time. "
                                        "Thank you, and have a good day.",
                                    lead_status="abandoned")

    if decision.action == ACTION_SUBMIT:
        state.terminal = decision.terminal
        state.terminal_reason = decision.reason
        state.handoff_completed = True
    elif decision.ends_call:
        state.terminal = decision.terminal
        state.terminal_reason = decision.reason

    return TurnResult(
        say=decision.say,
        action=decision.action,
        end_call=decision.ends_call,
        terminal=decision.terminal,
        reason=decision.reason,
        next_item=decision.next_item,
        missing_items=state.missing_items(),
        lead_status=decision.lead_status,
        intents=intents,
        recorded=changed,
        payload=decision.payload,
    )


class CallSession:
    """A whole call: owns the state, re-ask counters and the audit trail."""

    def __init__(self, *, customer_name: str = "the customer", language: str = "en-IN",
                 agent_name: str = "Agent", company_name: str = "the company") -> None:
        self.state = CallState()
        self.customer_name = customer_name
        self.language = language
        self.agent_name = agent_name
        self.company_name = company_name
        self.reasks: dict[str, int] = {}
        self.transcript: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    def handle(self, utterance: str, *, facts: Optional[dict[str, Any]] = None) -> TurnResult:
        result = process_turn(self.state, utterance, customer_name=self.customer_name,
                              facts=facts, reask_counts=self.reasks)
        self.transcript.append({
            "customer": utterance,
            "extracted_facts": facts or extract_facts(utterance),
            "intents": result.intents,
            "recorded": result.recorded,
            "agent_says": result.say,
            "action": result.action,
            "end_call": result.end_call,
            "terminal": result.terminal,
            "missing_items": result.missing_items,
        })
        return result

    def run(self, utterances: list[str]) -> list[TurnResult]:
        """Replay a list of customer utterances, stopping at the first terminal state."""
        out: list[TurnResult] = []
        for u in utterances:
            r = self.handle(u)
            out.append(r)
            if r.end_call:
                break
        return out

    # ------------------------------------------------------------------ #
    @property
    def terminal(self) -> str:
        return self.state.terminal or ""

    def lead_payload(self) -> dict[str, Any]:
        return {
            "lead_status": self.state.terminal or "in_progress",
            "reason": self.state.terminal_reason,
            "handoff_completed": self.state.handoff_completed,
            "facts": self.state.facts_payload(),
            "callback_time": self.state.callback_time,
            "language": self.language,
            "customer_name": self.customer_name,
            "unresolved_items": self.state.clarifications_pending,
            "audit_trail": self.state.facts_log,
            "transcript": self.transcript,
        }
