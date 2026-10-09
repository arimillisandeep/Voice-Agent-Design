"""Shared fixtures. Puts `src/` on the path so tests import the package directly."""

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from homecredit_lap.runtime import CallSession  # noqa: E402
from homecredit_lap.rules import MAX_LOAN_AMOUNT  # noqa: E402


@pytest.fixture
def session():
    return CallSession(customer_name="Rajesh Kumar", language="en-IN",
                       agent_name="Priya", company_name="Home Credit")


@pytest.fixture
def cap():
    return MAX_LOAN_AMOUNT


# A fully eligible answer set, one fact per turn, in checklist order.
QUALIFIED_SCRIPT = [
    ("It's a residential property", {"property_type": "residential"}),
    ("Solely in my name", {"ownership_status": "sole"}),
    ("Yes, the originals are available", {"documents_original": "yes"}),
    ("I need around fifty lakh", {"loan_amount": 5_000_000}),
    ("I'm salaried and my salary is credited to my bank account",
     {"occupation": "salaried", "income_mode": "bank"}),
    ("It's worth about one crore", {"market_value": 10_000_000}),
    ("Ten years", {"tenure_years": 10}),
]
