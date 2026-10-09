"""Tool layer exposed to the LLM.

Retell: each function below maps 1:1 to a tool in `platforms/retell.tools.json`.
Vapi:   same payloads; declare them as `functions` (server URL) or `messages`
        (client-only) in `platforms/vapi.tools.json`.

Rule: the LLM only ever *reports* what it heard. These functions decide what
happens next, so no threshold arithmetic ever runs inside the model.
"""

from __future__ import annotations

from typing import Any, Optional

from .parsing import detect_intents, extract_facts
from .rules import (ACTION_OFFER_CAP, ACTION_SUBMIT, ACTION_TRANSFER, MAX_LOAN_AMOUNT,
                    Decision, evaluate)
from .state import CallState

__all__ = [
    "LapAgentTools",
    "log_note",
    "record_eligibility_fact",
    "submit_eligibility_facts",
    "transfer_lead",
    "schedule_callback",
    "mark_do_not_call",
    "end_call",
]


class LapAgentTools:
    """Thin, platform-agnostic wrapper over :class:`CallState` + :func:`evaluate`.

    Every method returns a JSON-serialisable dict the platform can hand straight
    back to the LLM as the tool result.
    """

    def __init__(self, state: Optional[CallState] = None, *,
                 customer_name: str = "the customer",
                 language: str = "en-IN") -> None:
        self.state = state or CallState()
        self.customer_name = customer_name
        self.language = language
        self.notes: list[dict[str, str]] = []

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _result(self, decision: Decision, *, ends: Optional[bool] = None,
                **extra: Any) -> dict[str, Any]:
        """Shape a tool response.

        `ends` overrides Decision.ends_call. It is needed because `evaluate` reports
        ACTION_SUBMIT as *not* terminal (it is the instruction to call the submit tool),
        while `submit_eligibility_facts` completing really does end the call.
        """
        out: dict[str, Any] = {
            "action": decision.action,
            "say": decision.say,
            "say_key": decision.say_key,
            "language": self.language,
            "next_item": decision.next_item,
            "missing_items": self.state.missing_items(),
            "terminal": decision.terminal or None,
            "end_call": decision.ends_call if ends is None else ends,
        }
        if decision.reason:
            out["reason"] = decision.reason
        if decision.lead_status:
            out["lead_status"] = decision.lead_status
        if decision.payload:
            out.update(decision.payload)
        out.update(extra)
        return out

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _commit_terminal(self, decision: Decision) -> None:
        """Persist a terminal decision onto the state so the CRM payload is accurate.

        Skips ACTION_SUBMIT: that decision is only the instruction to call
        submit_eligibility_facts, which commits the qualified terminal itself.
        """
        if decision.ends_call and decision.terminal:
            self.state.terminal = decision.terminal
            self.state.terminal_reason = decision.reason

    # ------------------------------------------------------------------ #
    # tool: record_eligibility_fact
    # ------------------------------------------------------------------ #
    def record_eligibility_fact(self, key: str, value: Any, *,
                                source: str = "customer") -> dict[str, Any]:
        """Record one fact the customer just gave, then get the routing decision.

        Handles the ₹75 lakh cap negotiation transparently: recording an amount
        above the cap returns `action="offer_cap"` with the exact line to speak.
        """
        # CallState.record applies the cap normalisation, so accepting the cap is
        # handled identically here and in the runtime.
        changed = self.state.record(key, value, source=source)
        decision = evaluate(self.state, self.customer_name)
        self._commit_terminal(decision)
        return self._result(decision, recorded=key if changed else None, changed=changed)

    def record_facts(self, facts: dict[str, Any], *, source: str = "customer") -> dict[str, Any]:
        """Batch version — use when the customer bundles several answers (§12)."""
        changed = self.state.record_many(facts, source=source)
        decision = evaluate(self.state, self.customer_name)
        self._commit_terminal(decision)
        return self._result(decision, recorded=changed, changed=bool(changed))

    # ------------------------------------------------------------------ #
    # tool: submit_eligibility_facts
    # ------------------------------------------------------------------ #
    def submit_eligibility_facts(self) -> dict[str, Any]:
        """Final gate. Refuses to submit while an item is missing or ambiguous."""
        decision = evaluate(self.state, self.customer_name)
        if decision.action != ACTION_SUBMIT:
            return self._result(decision, submitted=False)
        self.state.terminal = decision.terminal
        self.state.terminal_reason = decision.reason
        self.state.handoff_completed = True
        return self._result(decision, ends=True, submitted=True,
                            lead_status="qualified_handoff", lead=decision.payload)

    # ------------------------------------------------------------------ #
    # tool: transfer_lead
    # ------------------------------------------------------------------ #
    def transfer_lead(self, specialist: str = "loan_transfer") -> dict[str, Any]:
        """Route an existing-loan / EMI-reduction case out of the fresh-loan flow."""
        if specialist == "loan_transfer":
            self.state.existing_property_loan = True
        decision = evaluate(self.state, self.customer_name)
        self.state.terminal = decision.terminal or "transfer"
        self.state.terminal_reason = decision.reason
        return self._result(decision, specialist=specialist)

    # ------------------------------------------------------------------ #
    # tool: schedule_callback
    # ------------------------------------------------------------------ #
    def schedule_callback(self, preferred_time: str) -> dict[str, Any]:
        """Book a callback. `preferred_time` is the customer's own words or an ISO slot."""
        self.state.busy = True
        self.state.record("callback_time", preferred_time)
        decision = evaluate(self.state, self.customer_name)
        self.state.terminal = decision.terminal or "callback"
        return self._result(decision, callback_time=preferred_time)

    # ------------------------------------------------------------------ #
    # tool: mark_do_not_call
    # ------------------------------------------------------------------ #
    def mark_do_not_call(self, reason: str = "customer_request") -> dict[str, Any]:
        self.state.do_not_call = True
        decision = evaluate(self.state, self.customer_name)
        self.state.terminal = "do_not_call"
        return self._result(decision, dnc_reason=reason)

    # ------------------------------------------------------------------ #
    # tool: end_call
    # ------------------------------------------------------------------ #
    def end_call(self, reason: str = "completed") -> dict[str, Any]:
        decision = evaluate(self.state, self.customer_name)
        if not decision.terminal:
            decision.terminal = "abandoned" if reason != "completed" else "declined"
        self.state.terminal = decision.terminal
        self.state.terminal_reason = reason
        return self._result(decision, end_reason=reason, end_call=True)

    # ------------------------------------------------------------------ #
    # tool: log_note
    # ------------------------------------------------------------------ #
    def log_note(self, note: str, tag: str = "general") -> dict[str, Any]:
        """Attach a free-text note to the call record.

        Observability only: it never changes routing, so the agent can log a customer's
        unrelated question, a correction, or sentiment without derailing the checklist.
        """
        self.notes.append({"tag": tag, "note": note})
        decision = evaluate(self.state, self.customer_name)
        return self._result(decision, logged=True, note_count=len(self.notes))

    # ------------------------------------------------------------------ #
    # backend-only helper (not an LLM tool): post-call CRM payload
    # ------------------------------------------------------------------ #
    def lead_payload(self) -> dict[str, Any]:
        return {
            "lead_status": (self.state.terminal or "in_progress"),
            "reason": self.state.terminal_reason,
            "handoff_completed": self.state.handoff_completed,
            "facts": self.state.facts_payload(),
            "callback_time": self.state.callback_time,
            "language": self.language,
            "customer_name": self.customer_name,
            "notes": self.notes,
            "audit_trail": self.state.facts_log,
        }


# --------------------------------------------------------------------------- #
# Module-level shims (some platforms want flat functions, not a class)
# --------------------------------------------------------------------------- #
def record_eligibility_fact(tools: LapAgentTools, key: str, value: Any) -> dict[str, Any]:
    return tools.record_eligibility_fact(key, value)


def submit_eligibility_facts(tools: LapAgentTools) -> dict[str, Any]:
    return tools.submit_eligibility_facts()


def transfer_lead(tools: LapAgentTools, specialist: str = "loan_transfer") -> dict[str, Any]:
    return tools.transfer_lead(specialist)


def schedule_callback(tools: LapAgentTools, preferred_time: str) -> dict[str, Any]:
    return tools.schedule_callback(preferred_time)


def mark_do_not_call(tools: LapAgentTools, reason: str = "customer_request") -> dict[str, Any]:
    return tools.mark_do_not_call(reason)


def end_call(tools: LapAgentTools, reason: str = "completed") -> dict[str, Any]:
    return tools.end_call(reason)


def log_note(tools: LapAgentTools, note: str, tag: str = "general") -> dict[str, Any]:
    return tools.log_note(note, tag)


# --------------------------------------------------------------------------- #
# Convenience: one-shot transcript classification (used by the CLI + tests)
# --------------------------------------------------------------------------- #
def classify_utterance(text: str) -> dict[str, Any]:
    """Return intents + extracted facts for a raw customer utterance."""
    return {"intents": detect_intents(text), "facts": extract_facts(text)}
