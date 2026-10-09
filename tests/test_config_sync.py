"""Guards against the classic failure mode of prompt-driven agents:

the YAML config, the Python constants and the system prompt text drifting apart.

If someone changes the cap in `config/product_rules.yaml` but not in the prompt,
these tests fail instead of the agent quietly quoting the wrong number on a live call.
"""

import re
from pathlib import Path

import yaml

from homecredit_lap.rules import SAY
from homecredit_lap.state import CHECKLIST_ITEMS, CHECKLIST_ORDER, MAX_LOAN_AMOUNT

ROOT = Path(__file__).resolve().parent.parent
PRODUCT_RULES = yaml.safe_load((ROOT / "config/product_rules.yaml").read_text(encoding="utf-8"))
STATE_SCHEMA = yaml.safe_load((ROOT / "config/state_schema.yaml").read_text(encoding="utf-8"))
LANGUAGES = yaml.safe_load((ROOT / "config/languages.yaml").read_text(encoding="utf-8"))
PROMPT = (ROOT / "prompt/system_prompt.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# YAML <-> Python constants
# --------------------------------------------------------------------------- #
def test_max_loan_amount_matches_yaml():
    assert MAX_LOAN_AMOUNT == PRODUCT_RULES["offer"]["max_loan_amount_inr"] == 75_00_000


def test_tenure_window_matches_yaml():
    from homecredit_lap.rules import MAX_TENURE_YEARS, MIN_TENURE_YEARS
    tenure = PRODUCT_RULES["eligibility"]["tenure_years"]
    assert (MIN_TENURE_YEARS, MAX_TENURE_YEARS) == (tenure["min"], tenure["max"]) == (3, 15)


def test_eligible_property_types_match_yaml():
    from homecredit_lap.rules import ELIGIBLE_PROPERTY_TYPES
    assert ELIGIBLE_PROPERTY_TYPES == set(PRODUCT_RULES["eligibility"]["property_type"]["eligible"])


def test_eligible_occupations_match_yaml():
    from homecredit_lap.rules import ELIGIBLE_OCCUPATIONS
    assert ELIGIBLE_OCCUPATIONS == set(PRODUCT_RULES["eligibility"]["occupation"]["eligible"])


def test_checklist_order_matches_yaml():
    assert list(CHECKLIST_ORDER) == PRODUCT_RULES["checklist_order"][:4] + [
        "occupation", "income_mode"] + PRODUCT_RULES["checklist_order"][5:]


def test_checklist_has_seven_items():
    """The prompt promises 7 items; occupation+income count as one."""
    assert len(CHECKLIST_ITEMS) == 7


def test_routing_priority_in_yaml_has_nine_steps():
    assert len(PRODUCT_RULES["routing_priority"]) == 9


def test_terminals_in_yaml_cover_the_engine():
    from homecredit_lap.state import Terminal
    declared = set(PRODUCT_RULES["terminals"])
    implemented = {t.value for t in Terminal if t.value}
    assert declared <= implemented, f"YAML declares unknown terminals: {declared - implemented}"


# --------------------------------------------------------------------------- #
# YAML <-> prompt text
# --------------------------------------------------------------------------- #
def test_prompt_states_the_75_lakh_cap():
    assert "75,00,000" in PROMPT or "₹75 lakh" in PROMPT


def test_prompt_states_the_tenure_window():
    assert re.search(r"3\s*(?:-|–|to)\s*15\s*year", PROMPT, re.IGNORECASE)


def test_prompt_marks_agricultural_as_disqualifying():
    assert "Agricultural" in PROMPT and "agricultural" in SAY["agricultural"]


def test_prompt_forbids_approval_language():
    for banned in ("approved", "guaranteed", "pre-approved"):
        assert banned in PROMPT, f"prompt must explicitly forbid {banned!r}"


def test_prompt_requires_preliminary_language():
    for required in ("may be eligible", "preliminary check", "next stage"):
        assert required in PROMPT


def test_prompt_forbids_invented_criteria():
    """§35: the prompt must list the criteria the agent may NOT invent."""
    for forbidden in ("interest rate", "Credit", "Age limit", "loan-to-value",
                      "processing fee", "Minimum income"):
        assert forbidden.lower() in PROMPT.lower(), f"missing guard on {forbidden!r}"


def test_prompt_never_leaks_internal_state_names_as_speech():
    """Internal flags must be described as internal, never as customer-facing text."""
    assert "Never mention states, flags, JSON, tools" in PROMPT


# --------------------------------------------------------------------------- #
# State schema <-> dataclass fields
# --------------------------------------------------------------------------- #
def test_state_schema_covers_every_dataclass_field():
    from dataclasses import fields
    from homecredit_lap.state import CallState
    declared = {k for k in STATE_SCHEMA if isinstance(STATE_SCHEMA[k], dict)}
    actual = {f.name for f in fields(CallState)}
    missing = actual - declared
    assert not missing, f"config/state_schema.yaml is missing: {sorted(missing)}"


def test_state_schema_records_are_well_formed():
    for key, spec in STATE_SCHEMA.items():
        if not isinstance(spec, dict):
            continue
        assert "type" in spec, f"{key} has no type"
        assert "default" in spec, f"{key} has no default"


def test_loan_amount_schema_carries_the_cap():
    assert STATE_SCHEMA["loan_amount"]["max"] == MAX_LOAN_AMOUNT


# --------------------------------------------------------------------------- #
# Language overlays
# --------------------------------------------------------------------------- #
def test_every_declared_language_has_an_overlay_or_is_english():
    lang_dir = ROOT / "prompt/languages"
    for lang in LANGUAGES["languages"]:
        if lang["overlay"] is None:
            assert lang["code"] == "en-IN", "only English may omit an overlay"
            continue
        assert (lang_dir / lang["overlay"]).exists(), f"missing overlay for {lang['code']}"


def test_overlays_define_the_required_sections():
    lang_dir = ROOT / "prompt/languages"
    required = ("## Register", "## Grammatical gender", "## Number and currency",
                "## Standard lines", "## Voice / TTS notes")
    for lang in LANGUAGES["languages"]:
        if not lang["overlay"]:
            continue
        text = (lang_dir / lang["overlay"]).read_text(encoding="utf-8")
        for section in required:
            assert section in text, f"{lang['code']} overlay is missing {section!r}"


def test_overlays_never_use_million():
    """Indian numbering only — 'million' would confuse both TTS and the customer."""
    lang_dir = ROOT / "prompt/languages"
    for lang in LANGUAGES["languages"]:
        if not lang["overlay"]:
            continue
        text = (lang_dir / lang["overlay"]).read_text(encoding="utf-8")
        assert "million" not in text.lower(), f"{lang['code']} overlay mentions 'million'"


def test_overlays_cover_the_core_conversation_lines():
    lang_dir = ROOT / "prompt/languages"
    core = ("Greeting", "Offer", "Documents", "Tenure", "Qualified", "Transfer", "Declines")
    for lang in LANGUAGES["languages"]:
        if not lang["overlay"]:
            continue
        text = (lang_dir / lang["overlay"]).read_text(encoding="utf-8")
        for line in core:
            assert line in text, f"{lang['code']} overlay lacks a {line!r} line"


def test_language_aliases_resolve_to_declared_codes():
    declared = {lang["code"] for lang in LANGUAGES["languages"]}
    for alias, code in LANGUAGES["accept_aliases"].items():
        assert code in declared, f"alias {alias!r} points at undeclared code {code!r}"


def test_gender_marking_values_are_valid():
    allowed = {"none", "weak", "moderate", "strong"}
    for lang in LANGUAGES["languages"]:
        assert lang["gender_marking"] in allowed


# --------------------------------------------------------------------------- #
# Tool declarations <-> Python tool layer
# --------------------------------------------------------------------------- #
def test_retell_tool_names_exist_in_the_python_layer():
    import json
    from homecredit_lap.tools import LapAgentTools
    tools = json.loads((ROOT / "platforms/retell.tools.json").read_text(encoding="utf-8"))
    implemented = set(dir(LapAgentTools))
    for tool in tools:
        if tool["type"] == "custom":
            assert tool["name"] in implemented, f"{tool['name']} declared but not implemented"


def test_retell_and_vapi_declare_the_same_custom_tools():
    import json
    retell = json.loads((ROOT / "platforms/retell.tools.json").read_text(encoding="utf-8"))
    vapi = json.loads((ROOT / "platforms/vapi.tools.json").read_text(encoding="utf-8"))
    r = {t["name"] for t in retell if t["type"] == "custom"}
    v = {t["function"]["name"] for t in vapi["tools"] if t["type"] == "function"}
    assert r == v, f"platform tool sets diverged: retell-only={r-v}, vapi-only={v-r}"


def test_record_tool_enum_matches_recordable_state_keys():
    import json
    from homecredit_lap.state import _RECORDABLE
    tools = json.loads((ROOT / "platforms/retell.tools.json").read_text(encoding="utf-8"))
    record = next(t for t in tools if t["name"] == "record_eligibility_fact")
    declared = set(record["parameters"]["properties"]["key"]["enum"])
    assert declared == set(_RECORDABLE), (
        f"tool enum drifted from state: declared-only={declared - _RECORDABLE}, "
        f"state-only={_RECORDABLE - declared}"
    )


def test_tools_json_is_valid():
    import json
    for name in ("retell.tools.json", "vapi.tools.json"):
        json.loads((ROOT / "platforms" / name).read_text(encoding="utf-8"))


def test_yaml_configs_parse():
    assert PRODUCT_RULES and STATE_SCHEMA and LANGUAGES
