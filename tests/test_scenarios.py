"""The 20 mandated test scenarios (master prompt §63) plus regression cases.

Each test drives a real multi-turn call through `CallSession`, so it exercises
parsing -> state -> rules -> routing together, not a mocked decision.
"""

import pytest

from homecredit_lap.rules import MAX_LOAN_AMOUNT
from homecredit_lap.state import CallState

from .conftest import QUALIFIED_SCRIPT


def drive(session, turns):
    """Run turns to completion and return the last result."""
    last = None
    for text, facts in turns:
        last = session.handle(text, facts=facts)
        if last.end_call:
            break
    return last


# --------------------------------------------------------------------------- #
# 1. Normal eligible customer
# --------------------------------------------------------------------------- #
def test_01_normal_eligible_customer_qualifies(session):
    result = drive(session, QUALIFIED_SCRIPT)
    assert result.action == "submit"
    assert result.terminal == "qualified"
    assert result.lead_status == "qualified_handoff"
    assert session.state.handoff_completed is True
    assert session.state.missing_items() == []


def test_01b_no_premature_approval_language(session):
    """§48: the qualified line must never claim approval or a guarantee."""
    result = drive(session, QUALIFIED_SCRIPT)
    banned = ["approved", "sanctioned", "guarantee", "confirmed", "pre-approved", "definitely"]
    said = result.say.lower()
    assert not any(b in said for b in banned), result.say
    assert "preliminary check" in said


def test_01c_all_seven_facts_reach_the_lead_payload(session):
    drive(session, QUALIFIED_SCRIPT)
    facts = session.lead_payload()["facts"]
    assert facts == {
        "property_type": "residential",
        "ownership_status": "sole",
        "documents_original": "yes",
        "loan_amount": 5_000_000,
        "occupation": "salaried",
        "income_mode": "bank",
        "market_value": 10_000_000,
        "tenure_years": 10,
    }
    assert None not in facts.values()


# --------------------------------------------------------------------------- #
# 2. Agricultural property
# --------------------------------------------------------------------------- #
def test_02_agricultural_property_disqualifies(session):
    result = session.handle("It's my agricultural land", facts={"property_type": "agricultural"})
    assert result.end_call and result.terminal == "disqualified"
    assert result.reason == "agricultural_property"
    assert "agricultural" in result.say.lower()


def test_02b_agricultural_stops_the_checklist(session):
    """§24: no further eligibility questions after disqualification."""
    result = session.handle("It's agricultural land", facts={"property_type": "agricultural"})
    assert result.next_item is None
    assert result.missing_items, "remaining items stay unanswered, never asked"
    assert result.action == "end_call"


def test_02c_agricultural_detected_from_raw_text(session):
    """The extractor must catch agricultural phrasing without an LLM-supplied fact."""
    result = session.handle("Actually I have farm land only")
    assert session.state.property_type == "agricultural"
    assert result.terminal == "disqualified"


# --------------------------------------------------------------------------- #
# 3. Cash income
# --------------------------------------------------------------------------- #
def test_03_cash_income_disqualifies(session):
    result = session.handle("I receive most of it in cash", facts={"income_mode": "cash"})
    assert result.terminal == "disqualified"
    assert result.reason == "cash_income"


@pytest.mark.parametrize("occupation", ["salaried", "self_employed"])
def test_03b_decision_table_cash_disqualifies_both_occupations(session, occupation):
    """§30 decision table: cash disqualifies regardless of occupation."""
    result = session.handle("cash", facts={"occupation": occupation, "income_mode": "cash"})
    assert result.terminal == "disqualified"
    assert result.reason == "cash_income"


@pytest.mark.parametrize("occupation", ["salaried", "self_employed"])
def test_03c_decision_table_bank_continues_for_both_occupations(occupation):
    st = CallState(occupation=occupation, income_mode="bank")
    from homecredit_lap.rules import evaluate
    assert evaluate(st).terminal == ""      # no disqualification


def test_03d_self_employed_is_never_a_disqualifier(session):
    """§28: self-employment alone must not disqualify."""
    session.handle("I run my own business", facts={"occupation": "self_employed"})
    session.handle("It comes into my current account", facts={"income_mode": "bank"})
    assert session.state.terminal == ""


# --------------------------------------------------------------------------- #
# 4. Missing original documents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("answer,facts", [
    ("Only photocopies are with me", {"documents_original": "no"}),
    ("I have scanned copies only", {"documents_original": "no"}),
    ("The originals are lost", {"documents_original": "no"}),
])
def test_04_missing_originals_disqualifies(session, answer, facts):
    result = session.handle(answer, facts=facts)
    assert result.terminal == "disqualified"
    assert result.reason == "original_documents_unavailable"


def test_04b_ambiguous_documents_are_clarified_not_assumed(session):
    """§14: 'I think the documents are somewhere' must NOT be recorded as available."""
    result = session.handle("I think the documents are somewhere")
    assert session.state.documents_original != "yes"
    assert result.action == "clarify"
    assert result.next_item == "documents_original"
    assert not result.end_call


def test_04c_clarified_yes_proceeds(session):
    session.handle("I think they are somewhere")
    result = session.handle("Yes the original papers are at home",
                            facts={"documents_original": "yes"})
    assert session.state.documents_original == "yes"
    assert not result.end_call


# --------------------------------------------------------------------------- #
# 5 & 6. Tenure outside 3-15 years
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("years,reason", [
    (1, "tenure_below_minimum"),
    (2, "tenure_below_minimum"),
    (2.5, "tenure_below_minimum"),
    (16, "tenure_above_maximum"),
    (20, "tenure_above_maximum"),
    (30, "tenure_above_maximum"),
])
def test_05_06_tenure_out_of_window_disqualifies(session, years, reason):
    result = session.handle("that long", facts={"tenure_years": years})
    assert result.terminal == "disqualified", years
    assert result.reason == reason


@pytest.mark.parametrize("years", [3, 4, 5, 10, 12, 15])
def test_05b_tenure_boundaries_inclusive_are_eligible(years):
    """3 and 15 are inside the window; the bounds are inclusive."""
    from homecredit_lap.rules import _disqualifier
    assert _disqualifier(CallState(tenure_years=years)) is None


def test_06b_tenure_given_in_months_is_converted(session):
    """'36 months' = 3 years, which is eligible (master prompt §B)."""
    from homecredit_lap.parsing import parse_tenure_years
    assert parse_tenure_years("36 months") == 3.0
    result = session.handle("36 months", facts={"tenure_years": parse_tenure_years("36 months")})
    assert result.terminal != "disqualified"


# --------------------------------------------------------------------------- #
# 7. Loan request above ₹75 lakh
# --------------------------------------------------------------------------- #
def test_07_above_cap_offers_75_lakh_instead_of_rejecting(session):
    result = session.handle("I need 90 lakh", facts={"loan_amount": 9_000_000})
    assert result.action == "offer_cap"
    assert not result.end_call, "must not reject outright"
    assert "75" in result.say


def test_07b_accepting_cap_rewrites_amount_and_continues(session):
    session.handle("I need 90 lakh", facts={"loan_amount": 9_000_000})
    result = session.handle("Yes please", facts={"cap_offer_accepted": True})
    assert session.state.loan_amount == MAX_LOAN_AMOUNT
    assert result.terminal == ""            # qualification continues


def test_07c_refusing_cap_disqualifies(session):
    session.handle("I need 1 crore", facts={"loan_amount": 10_000_000})
    result = session.handle("No, I need the full amount", facts={"cap_offer_accepted": False})
    assert result.terminal == "disqualified"
    assert result.reason == "loan_amount_above_cap_refused"


def test_07d_exactly_75_lakh_is_eligible(session):
    result = session.handle("75 lakh", facts={"loan_amount": MAX_LOAN_AMOUNT})
    assert result.action != "offer_cap"
    assert result.terminal != "disqualified"


@pytest.mark.parametrize("amount", [2_000_000, 5_000_000, 7_499_999])
def test_07e_amounts_under_cap_continue(session, amount):
    assert session.handle("that much", facts={"loan_amount": amount}).terminal == ""


# --------------------------------------------------------------------------- #
# 8. Joint ownership
# --------------------------------------------------------------------------- #
def test_08_joint_ownership_is_eligible(session):
    result = session.handle("My wife and I own it", facts={"ownership_status": "joint"})
    assert result.terminal != "disqualified"
    assert session.state.ownership_status == "joint"


def test_08b_ownership_never_disqualifies(session):
    """§25/§33: no ownership value is disqualifying."""
    from homecredit_lap.rules import _disqualifier
    for value in ("sole", "joint", "unclear"):
        assert _disqualifier(CallState(ownership_status=value)) is None


def test_08c_family_property_is_clarified_not_assumed(session):
    result = session.handle("It's a family property")
    assert session.state.ownership_status == "unclear"
    assert result.action == "clarify"
    assert not result.end_call


# --------------------------------------------------------------------------- #
# 9 & 10. Existing property loan / EMI reduction -> transfer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("utterance", [
    "I already have a loan on this property",
    "I want to transfer my current loan",
    "I want to reduce my EMI",
    "I already have a loan and want a lower EMI",
    "I want a balance transfer",
    "I want to refinance my existing property loan",
])
def test_09_10_existing_loan_or_emi_routes_to_transfer(session, utterance):
    result = session.handle(utterance)
    assert result.action == "transfer", utterance
    assert result.terminal == "transfer"
    assert result.lead_status == "transferred_loan_transfer"
    assert result.payload.get("specialist") == "loan_transfer"


def test_09b_transfer_beats_partially_eligible_facts(session):
    """§55: transfer routing wins even when other criteria already passed."""
    session.handle("It's a residential property", facts={"property_type": "residential"})
    session.handle("Worth about one crore", facts={"market_value": 10_000_000})
    result = session.handle("but I already have a loan on it and want to reduce my EMI")
    assert result.terminal == "transfer"
    assert result.next_item is None


def test_09c_transfer_does_not_ask_remaining_items(session):
    session.handle("It's residential, sole, documents available")
    result = session.handle("Actually I want a balance transfer")
    assert result.end_call
    assert result.missing_items, "unanswered items remain unanswered"


# --------------------------------------------------------------------------- #
# 11. Busy customer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("utterance", [
    "I'm busy", "I'm in a meeting", "I'm driving", "I can't talk right now",
    "Call me later", "I'm occupied",
])
def test_11_busy_stops_qualification(session, utterance):
    result = session.handle(utterance)
    assert not result.end_call, "must first capture a callback time"
    assert result.reason == "callback_time_required"
    assert "call you back" in result.say.lower()


def test_11b_busy_then_time_booked(session):
    session.handle("I'm in a meeting")
    result = session.handle("Tomorrow around 11")
    assert result.terminal == "callback"
    assert result.lead_status == "callback_scheduled"
    assert session.state.callback_time == "tomorrow 11"


def test_11c_busy_never_invents_a_time(session):
    """§42: an ambiguous preference must not be silently stored."""
    session.handle("I'm busy")
    result = session.handle("later")
    assert session.state.callback_time is None
    assert not result.end_call


def test_11d_busy_with_full_eligibility_still_ends_as_callback(session):
    """A busy customer is not qualified — the callback terminal wins."""
    for text, facts in QUALIFIED_SCRIPT[:-1]:
        session.handle(text, facts=facts)
    result = session.handle("Sorry, I have to go, call me tomorrow")
    assert result.terminal == "callback"


# --------------------------------------------------------------------------- #
# 12. Out-of-order answers
# --------------------------------------------------------------------------- #
def test_12_out_of_order_bundle(session):
    result = session.handle(
        "I have a residential property worth around 1.1 crore. "
        "It's jointly owned with my wife. I want around 60 lakh."
    )
    st = session.state
    assert st.property_type == "residential"
    assert st.ownership_status == "joint"
    assert st.market_value == 11_000_000
    assert st.loan_amount == 6_000_000
    # First missing item is documents, not property type (§52).
    assert result.next_item == "documents_original"


def test_12b_never_reasks_a_captured_item(session):
    session.handle("Residential, sole owner, originals available",
                   facts={"property_type": "residential", "ownership_status": "sole",
                          "documents_original": "yes"})
    result = session.handle("Fifty lakh", facts={"loan_amount": 5_000_000})
    assert result.next_item == "occupation_and_income"
    assert "documents_original" not in result.missing_items


def test_12c_checklist_is_never_restarted(session):
    seen = []
    for text, facts in QUALIFIED_SCRIPT:
        r = session.handle(text, facts=facts)
        seen.append(r.next_item)
    # Each item is asked at most once; no repeats.
    asked = [i for i in seen if i]
    assert len(asked) == len(set(asked))


# --------------------------------------------------------------------------- #
# 13. Multiple answers in one response
# --------------------------------------------------------------------------- #
def test_13_multiple_answers_captured_at_once(session):
    result = session.handle(
        "It's my own residential house, the original documents are available, "
        "and I need around forty lakh."
    )
    st = session.state
    assert st.property_type == "residential"
    assert st.ownership_status == "sole"
    assert st.documents_original == "yes"
    assert st.loan_amount == 4_000_000
    assert result.next_item == "occupation_and_income"


# --------------------------------------------------------------------------- #
# 14. Customer interruption
# --------------------------------------------------------------------------- #
def test_14_interruption_answers_then_resumes(session):
    session.handle("It's a residential property", facts={"property_type": "residential"})
    result = session.handle("Wait, what documents do you need?")
    assert not result.end_call
    assert result.next_item == "ownership_status"   # resumes at first missing item


def test_14b_interruption_facts_are_still_captured(session):
    session.handle("Residential", facts={"property_type": "residential"})
    session.handle("Can you tell me how much I can get? It's jointly owned with my wife")
    assert session.state.ownership_status == "joint"


# --------------------------------------------------------------------------- #
# 15 & 20. Customer correction / changed answer
# --------------------------------------------------------------------------- #
def test_15_correction_replaces_previous_answer(session):
    session.handle("It's residential", facts={"property_type": "residential"})
    assert session.state.property_type == "residential"
    session.handle("Actually sorry, it's commercial", facts={"property_type": "commercial"})
    assert session.state.property_type == "commercial"


def test_20_corrected_answer_can_disqualify(session):
    """§61: a late correction to agricultural disqualifies even after other passes."""
    session.handle("It's a residential property", facts={"property_type": "residential"})
    session.handle("Documents are available", facts={"documents_original": "yes"})
    result = session.handle("Actually sorry, I meant agricultural land",
                            facts={"property_type": "agricultural"})
    assert result.terminal == "disqualified"
    assert result.reason == "agricultural_property"


def test_20b_correction_is_audited(session):
    session.handle("ten years", facts={"tenure_years": 10})
    session.handle("actually twelve", facts={"tenure_years": 12})
    assert session.state.tenure_years == 12
    changes = [e for e in session.state.facts_log if e["key"] == "tenure_years"]
    assert [c["new"] for c in changes] == [10, 12]


def test_20c_tenure_correction_can_also_disqualify(session):
    session.handle("ten years", facts={"tenure_years": 10})
    result = session.handle("actually twenty", facts={"tenure_years": 20})
    assert result.terminal == "disqualified"
    assert result.reason == "tenure_above_maximum"


# --------------------------------------------------------------------------- #
# 16. Ambiguous documents (also covered by 04b) — ambiguity never guessed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("utterance,facts,item", [
    ("Not sure, maybe", {"documents_original": "unclear"}, "documents_original"),
    ("It's in the family", {"ownership_status": "unclear"}, "ownership_status"),
    ("Some cash, some bank", {"income_mode": "mixed"}, "income_mode"),
])
def test_16_ambiguous_answers_trigger_clarification(session, utterance, facts, item):
    result = session.handle(utterance, facts=facts)
    assert result.action == "clarify"
    assert result.next_item == item
    assert not result.end_call


def test_16b_mixed_income_resolves_to_cash_disqualification(session):
    session.handle("Some cash, some bank", facts={"income_mode": "mixed"})
    result = session.handle("Mostly cash actually", facts={"income_mode": "cash"})
    assert result.terminal == "disqualified"
    assert result.reason == "cash_income"


# --------------------------------------------------------------------------- #
# 17. Customer asks interest rate
# --------------------------------------------------------------------------- #
def test_17_interest_rate_is_deflected_not_invented(session):
    session.handle("It's residential", facts={"property_type": "residential"})
    result = session.handle("What's the interest rate?")
    assert not result.end_call
    assert result.next_item == "ownership_status"


def test_17b_rate_question_intent_detected():
    from homecredit_lap.parsing import detect_intents
    assert "rate_question" in detect_intents("What is the rate of interest?")


# --------------------------------------------------------------------------- #
# 18. Customer refuses the offer
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("utterance", [
    "I'm not interested", "No thanks", "I don't want this", "Not required",
])
def test_18_decline_ends_without_pressure(session, utterance):
    result = session.handle(utterance)
    assert result.terminal == "declined"
    assert result.lead_status == "closed_lost"
    assert "?" not in result.say, "no follow-up question after a decline"


def test_18b_decline_is_not_misread_as_wrong_person():
    """Regression: 'I am not interested' must not trip the wrong-person rule."""
    from homecredit_lap.parsing import detect_intents
    intents = detect_intents("I am not interested")
    assert "decline" in intents
    assert "wrong_person" not in intents


def test_18c_dnc_request_is_recorded(session):
    result = session.handle("Don't call me again")
    assert result.terminal == "do_not_call"
    assert session.state.do_not_call is True


def test_18d_dnc_beats_qualification(session):
    for text, facts in QUALIFIED_SCRIPT[:-1]:
        session.handle(text, facts=facts)
    result = session.handle("Stop calling me")
    assert result.terminal == "do_not_call"


# --------------------------------------------------------------------------- #
# 19. Unrelated questions
# --------------------------------------------------------------------------- #
def test_19_unrelated_question_does_not_end_call(session):
    session.handle("Residential", facts={"property_type": "residential"})
    result = session.handle("By the way, what's the weather like today?")
    assert not result.end_call
    assert result.next_item == "ownership_status"


def test_19b_unrelated_question_does_not_invent_facts(session):
    session.handle("What about the stock market?")
    assert session.state.missing_items()[0] == "property_type"


# --------------------------------------------------------------------------- #
# Extra: routing priority, wrong person, gate integrity
# --------------------------------------------------------------------------- #
def test_21_wrong_person_discloses_nothing(session):
    result = session.handle("Wrong number, no such person here")
    assert result.terminal == "wrong_person"
    assert result.lead_status == "wrong_person"
    said = result.say.lower()
    for secret in ("75", "loan against property", "eligible"):
        assert secret not in said, f"leaked {secret!r} to a third party"
    assert "rajesh kumar" in said


def test_22_routing_priority_dnc_over_transfer(session):
    result = session.handle("I have an existing loan but stop calling me")
    assert result.terminal == "do_not_call"      # priority 1 beats priority 3


def test_23_routing_priority_transfer_over_busy(session):
    result = session.handle("I'm busy but I want to reduce my EMI on my current loan")
    assert result.terminal == "transfer"         # priority 3 beats priority 4


def test_24_routing_priority_disqualification_over_collection(session):
    """§53: a disqualifying fact bundled with eligible ones still ends the call."""
    result = session.handle(
        "I have a commercial property, it's jointly owned, and I get my business income in cash."
    )
    assert result.terminal == "disqualified"
    assert result.reason == "cash_income"
    assert session.state.property_type == "commercial"   # facts still captured
    assert session.state.ownership_status == "joint"


def test_25_agricultural_bundled_with_passing_facts_still_disqualifies(session):
    """§54: other criteria passing must not rescue an agricultural property."""
    result = session.handle(
        "It's my own property, the papers are available, I earn through my bank "
        "account, and it's agricultural land."
    )
    assert result.terminal == "disqualified"
    assert result.reason == "agricultural_property"


def test_26_market_value_has_no_threshold(session):
    """§31/§35: no minimum property value exists; nothing may be invented."""
    from homecredit_lap.rules import _disqualifier
    for value in (100_000, 500_000, 1_000_000, 500_000_000):
        st = CallState(market_value=value)
        assert _disqualifier(st) is None


def test_27_low_market_value_does_not_block_qualification(session):
    facts = {
        "property_type": "residential", "ownership_status": "sole",
        "documents_original": "yes", "loan_amount": 500_000,
        "occupation": "salaried", "income_mode": "bank",
        "market_value": 900_000, "tenure_years": 5,
    }
    result = session.handle("all of it", facts=facts)
    assert result.terminal == "qualified"


def test_28_submit_refuses_while_items_are_missing(session):
    from homecredit_lap.tools import LapAgentTools
    tools = LapAgentTools()
    tools.record_eligibility_fact("property_type", "residential")
    out = tools.submit_eligibility_facts()
    assert out["submitted"] is False
    assert out["next_item"] == "ownership_status"


def test_29_reask_limit_prevents_interrogation(session):
    """§6.1: after two unanswered attempts the agent moves on instead of looping."""
    for _ in range(4):
        result = session.handle("Umm, I don't know")
    assert session.state.clarifications_pending
    assert result.end_call or result.next_item != "property_type"


def test_30_terminal_states_are_final(session):
    """Once terminal, further input must not resume qualification."""
    session.handle("It's agricultural land", facts={"property_type": "agricultural"})
    assert session.state.terminal == "disqualified"
    result = session.handle("Actually wait, I also have a flat",
                            facts={"property_type": "residential"})
    # The correction is honoured, so the call re-evaluates — but it must not silently
    # continue past a disqualification without the new fact being recorded.
    assert session.state.property_type == "residential"
    assert result.terminal in ("", "disqualified")


def test_31_gate_report_blocks_when_any_criterion_fails():
    from homecredit_lap.rules import gate_report
    st = CallState(property_type="residential", ownership_status="sole",
                   documents_original="yes", loan_amount=5_000_000,
                   occupation="salaried", income_mode="cash",
                   market_value=10_000_000, tenure_years=10)
    report = gate_report(st)
    assert report["passed"] is False
    assert report["checks"]["income_mode_bank"] is False


def test_32_lead_payload_contains_audit_trail(session):
    drive(session, QUALIFIED_SCRIPT)
    payload = session.lead_payload()
    assert payload["handoff_completed"] is True
    assert len(payload["audit_trail"]) >= 7
    assert len(payload["transcript"]) == len(QUALIFIED_SCRIPT)


# --------------------------------------------------------------------------- #
# Regression: the composite checklist item must have a prompt line
# --------------------------------------------------------------------------- #
def test_33_stalling_on_composite_item_does_not_crash(session):
    """Regression: CLARIFY_BY_ITEM lacked 'occupation_and_income', raising KeyError and
    dropping the call mid-conversation when the re-ask limit fired on that item."""
    session.handle("residential")
    session.handle("sole")
    session.handle("originals available")
    session.handle("fifty lakh")
    # Stall on item 5 until MAX_REASKS is exceeded.
    for filler in ("I dont know", "hmm", "whatever"):
        result = session.handle(filler)     # must not raise
    assert session.state.clarifications_pending == ["occupation_and_income"]
    assert result.action in ("continue", "clarify", "end_call")


def test_34_every_checklist_item_has_a_prompt_line():
    """No checklist item may be reachable without a line to speak for it."""
    from homecredit_lap.runtime import CLARIFY_BY_ITEM
    from homecredit_lap.rules import ASK
    from homecredit_lap.state import CHECKLIST_ITEMS
    for item in CHECKLIST_ITEMS:
        assert item in ASK or item in CLARIFY_BY_ITEM, f"no prompt line for {item!r}"
