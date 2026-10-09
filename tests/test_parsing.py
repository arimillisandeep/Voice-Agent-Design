"""Unit tests for the spoken-language parsing layer."""

import pytest

from homecredit_lap.parsing import (
    classify_utterance,
    detect_intents,
    extract_facts,
    parse_amount,
    parse_callback_time,
    parse_documents,
    parse_income_mode,
    parse_occupation,
    parse_ownership,
    parse_property_type,
    parse_tenure_years,
)


# --------------------------------------------------------------------------- #
# Amounts — master prompt §41 (Indian numbering)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("10 lakh", 1_000_000),
    ("50 lakh", 5_000_000),
    ("75 lakh", 7_500_000),
    ("1 crore", 10_000_000),
    ("1.2 crore", 12_000_000),
    ("seventy-five lakhs", 7_500_000),
    ("seventy five lakh", 7_500_000),
    ("ninety lakh", 9_000_000),
    ("20 thousand", 20_000),
    ("fifty", 5_000_000),                 # bare number in an amount answer = lakhs
    ("पचास लाख", 5_000_000),
    ("एक करोड़", 10_000_000),
])
def test_parse_amount_indian_conventions(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("60,00,000", 6_000_000),             # Indian digit grouping
    ("₹60,00,000", 6_000_000),
    ("75,00,000", 7_500_000),
    ("1,00,00,000", 10_000_000),
    ("1,00,000", 100_000),
    ("6,000,000", 6_000_000),             # ISO grouping gives the same figure
    ("Rs. 50,00,000", 5_000_000),
    ("5000000", 5_000_000),
])
def test_parse_amount_digit_grouping(text, expected):
    """Regression: grouped digits must not be multiplied by the lakh default."""
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", ["two minutes", "5 days", "3 questions", "in 1 hour"])
def test_parse_amount_rejects_time_and_quantity_units(text):
    """Regression: 'repay over two years' must not become a ₹2 lakh loan."""
    assert parse_amount(text) is None


def test_parse_amount_additive_phrase():
    assert parse_amount("one crore twenty lakh") == 12_000_000


def test_parse_amount_does_not_sum_across_clauses():
    """Regression: 'worth 75 lakh AND I need 40 lakh' is two figures, not 1.15 crore."""
    assert parse_amount("worth 75,00,000 and I need 40 lakh") == 7_500_000


def test_parse_amount_absolute_numeral_not_scaled():
    assert parse_amount("I need 500000") == 500_000


def test_parse_amount_none_for_no_number():
    assert parse_amount("I'm not sure yet") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None


# --------------------------------------------------------------------------- #
# Tenure
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("ten years", 10.0),
    ("10 years", 10.0),
    ("15 yrs", 15.0),
    ("two years", 2.0),
    ("twenty years", 20.0),
    ("36 months", 3.0),                   # months are converted
    ("डेढ़ साल", 1.5),
])
def test_parse_tenure(text, expected):
    assert parse_tenure_years(text) == expected


@pytest.mark.parametrize("text", ["a couple of years", "long term", "as long as possible", ""])
def test_parse_tenure_ambiguous_returns_none(text):
    """Ambiguous tenure must come back unknown so the agent asks again."""
    assert parse_tenure_years(text) is None


# --------------------------------------------------------------------------- #
# Property type
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("my house", "residential"),
    ("my flat", "residential"),
    ("apartment", "residential"),
    ("my shop", "commercial"),
    ("my office", "commercial"),
    ("showroom", "commercial"),
    ("my factory", "industrial"),
    ("manufacturing unit", "industrial"),
    ("agricultural land", "agricultural"),
    ("my farm land", "agricultural"),
    ("खेत है", "agricultural"),
])
def test_parse_property_type(text, expected):
    assert parse_property_type(text) == expected


# --------------------------------------------------------------------------- #
# Ownership
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("It's only in my name", "sole"),
    ("solely mine", "sole"),
    ("It's my own residential house", "sole"),
    ("it's mine", "sole"),
    ("My wife and I own it", "joint"),
    ("jointly owned with my brother", "joint"),
    ("mere bhai ke saath", "joint"),
    ("my father and I both", "joint"),
])
def test_parse_ownership(text, expected):
    assert parse_ownership(text) == expected


@pytest.mark.parametrize("text", ["yes", "hmm", "I don't know"])
def test_parse_ownership_never_guesses(text):
    assert parse_ownership(text) is None


@pytest.mark.parametrize("text", ["It's a family property", "ancestral property"])
def test_parse_ownership_family_property_is_unclear(text):
    """§25: 'family property' must be clarified, not assumed joint."""
    assert parse_ownership(text) == "unclear"


def test_parse_ownership_business_does_not_imply_property():
    """'I run my own business' is about work, not title."""
    assert parse_ownership("I run my own business") is None


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("yes the originals are at home", "yes"),
    ("original papers available", "yes"),
    ("only photocopies", "no"),
    ("I have scanned copies", "no"),
    ("they are lost", "no"),
    ("I think the documents are somewhere", "unclear"),
])
def test_parse_documents(text, expected):
    assert parse_documents(text) == expected


# --------------------------------------------------------------------------- #
# Occupation / income
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("I work for a company", "salaried"),
    ("I'm employed with a bank", "salaried"),
    ("government job", "salaried"),
    ("naukri karta hoon", "salaried"),
    ("I run my own business", "self_employed"),
    ("I'm a freelancer", "self_employed"),
    ("proprietor of a shop", "self_employed"),
    ("I am a student", "none"),
    ("I'm retired", "none"),
])
def test_parse_occupation(text, expected):
    assert parse_occupation(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("My salary is credited to my bank", "bank"),
    ("My business income comes into my account", "bank"),
    ("I receive most of it in cash", "cash"),
    ("नकद आता है", "cash"),
    ("some cash and some bank", "mixed"),
])
def test_parse_income_mode(text, expected):
    assert parse_income_mode(text) == expected


# --------------------------------------------------------------------------- #
# Callback time
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("Tomorrow around 11", "tomorrow 11"),
    ("call me in the evening", "evening"),
    ("after 30 minutes", "in 30 minutes"),
    ("in 1 hour", "in 1 hour"),
    ("kal subah 10 baje", "kal 10"),
    ("next monday", "monday"),
    ("5 pm", "5 pm"),
    ("tomorrow 3:30 pm", "tomorrow 3:30 pm"),
])
def test_parse_callback_time(text, expected):
    assert parse_callback_time(text) == expected


@pytest.mark.parametrize("text", ["later", "anytime", "some time", ""])
def test_parse_callback_time_ambiguous_is_none(text):
    """§42: never invent a time the customer did not give."""
    assert parse_callback_time(text) is None


def test_parse_callback_time_ignores_loan_amounts():
    """Regression: an amount answer must not be misread as a callback hour."""
    assert parse_callback_time("I need 50 lakh") is None


# --------------------------------------------------------------------------- #
# Intents
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text,expected", [
    ("I'm not interested", "decline"),
    ("I am in a meeting", "busy"),
    ("Sorry, I have to go, call me tomorrow", "busy"),
    ("don't call me again", "dnc"),
    ("wrong number", "wrong_person"),
    ("what's the interest rate", "rate_question"),
    ("I want a balance transfer", "transfer"),
])
def test_detect_intents(text, expected):
    assert expected in detect_intents(text)


def test_decline_is_not_wrong_person():
    """Regression: 'I am not interested' used to trip the wrong-person rule."""
    assert "wrong_person" not in detect_intents("I am not interested")


def test_existing_loan_and_emi_detected_together():
    intents = detect_intents("I already have a loan on this property and want to reduce my EMI")
    assert "existing_loan" in intents and "emi_reduction" in intents


# --------------------------------------------------------------------------- #
# Bundled extraction
# --------------------------------------------------------------------------- #
def test_extract_out_of_order_bundle():
    facts = extract_facts(
        "I have a residential property worth around one crore. "
        "It's jointly owned with my wife and I need about fifty lakh."
    )
    assert facts["property_type"] == "residential"
    assert facts["ownership_status"] == "joint"
    assert facts["market_value"] == 10_000_000
    assert facts["loan_amount"] == 5_000_000


def test_extract_separates_value_from_loan_amount():
    """Regression: 'worth X and need Y' must not collapse into one field."""
    facts = extract_facts("It is worth 60,00,000 and I need 25 lakh")
    assert facts["market_value"] == 6_000_000
    assert facts["loan_amount"] == 2_500_000


def test_extract_multiple_answers():
    facts = extract_facts(
        "It's my own residential house, the original documents are available, "
        "and I need around forty lakh."
    )
    assert facts["property_type"] == "residential"
    assert facts["ownership_status"] == "sole"
    assert facts["documents_original"] == "yes"
    assert facts["loan_amount"] == 4_000_000


def test_extract_cash_income_bundle():
    facts = extract_facts(
        "I have a commercial property, it's jointly owned, "
        "and I get my business income in cash."
    )
    assert facts["income_mode"] == "cash"
    assert facts["property_type"] == "commercial"
    assert facts["ownership_status"] == "joint"


def test_extract_tenure_does_not_leak_into_amount():
    """Regression: 'over two years' used to produce a ₹2 lakh loan amount."""
    facts = extract_facts("I'd like to repay it over two years.")
    assert facts.get("tenure_years") == 2.0
    assert "loan_amount" not in facts


def test_extract_never_guesses_absent_facts():
    facts = extract_facts("Hello, yes this is he.")
    assert "property_type" not in facts
    assert "documents_original" not in facts


def test_classify_utterance_returns_intents_and_facts():
    out = classify_utterance("I'm in a meeting")
    assert "busy" in out["intents"]
    assert isinstance(out["facts"], dict)


# --------------------------------------------------------------------------- #
# Regressions found while building the browser demo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", [
    "Yes the originals are available",
    "the originals are with me",
    "originals are in my locker",
    "हां, ओरिजिनल डॉक्यूमेंट हैं",
])
def test_originals_alone_is_a_documents_answer(text):
    """Customers say 'the originals are available' without the word 'documents'."""
    assert extract_facts(text).get("documents_original") == "yes"


@pytest.mark.parametrize("text", [
    "I have only photocopies",
    "only xerox copies",
    "I have scanned copies",
    "फोटोकॉपी ही हैं",
])
def test_negative_documents_answers_are_detected(text):
    """A 'no' answer must be recognised as a documents answer, not ignored."""
    assert extract_facts(text).get("documents_original") == "no"


@pytest.mark.parametrize("text", [
    "documents are at home",
    "papers are at home",
    "I have a home loan",
    "my home loan EMI",
    "from my house",
    "stay at home",
])
def test_location_phrases_do_not_imply_property_type(text):
    """Regression: 'at home' / 'home loan' used to record residential property."""
    assert parse_property_type(text) is None


@pytest.mark.parametrize("text,expected", [
    ("my own house", "residential"),
    ("It is my home", "residential"),
    ("I have a house in Hyderabad", "residential"),
    ("मेरा घर है", "residential"),
])
def test_genuine_residential_statements_still_detected(text, expected):
    assert parse_property_type(text) == expected


@pytest.mark.parametrize("text", [
    "It is my own residential house and the originals are available",
    "my own house",
    "khud ka ghar hai",
    "It is my own property",
    "it's my shop",
    "my shop is commercial",
])
def test_property_phrasing_does_not_imply_occupation(text):
    """Regression: 'my own house' used to record the customer as self-employed."""
    assert "occupation" not in extract_facts(text)
    assert parse_occupation(text) is None


@pytest.mark.parametrize("text", [
    "self employed", "self-employed", "I am self employed", "I run my own business",
    "I have a shop", "own a shop", "I have my own business",
])
def test_self_employed_phrase_is_not_read_as_salaried(text):
    """Regression: 'self employed' contains 'employed' and was classified salaried."""
    assert parse_occupation(text) == "self_employed"


@pytest.mark.parametrize("text", [
    "I work for a company", "I'm employed with a bank", "government job",
    "naukri karta hoon", "I am a teacher", "private company employee",
])
def test_salaried_phrases_still_detected(text):
    assert parse_occupation(text) == "salaried"


def test_productive_turns_do_not_trip_the_reask_limit():
    """Regression: answering other questions must not abandon a pending item."""
    from homecredit_lap.runtime import CallSession
    s = CallSession()
    turns = [
        "It's a residential property",
        "Solely in my name",
        "Yes the originals are available",
        "I need around fifty lakh",
        "I'm salaried and my salary is credited to my bank account",
        "It's worth about one crore",
        "Ten years",
    ]
    results = [s.handle(t) for t in turns]
    assert results[-1].terminal == "qualified", results[-1].terminal
    assert s.state.documents_original == "yes"
    assert s.state.clarifications_pending == []
