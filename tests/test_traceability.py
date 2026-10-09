"""Guards the traceability matrix itself.

If someone renames a prompt heading, deletes a test, or moves a config key without
updating `docs/traceability.yaml`, these tests fail — so the coverage report cannot
quietly drift away from the code it claims to describe.
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "src"))

import verify_coverage as vc  # noqa: E402

MATRIX = yaml.safe_load((ROOT / "docs/traceability.yaml").read_text(encoding="utf-8"))
SECTIONS = MATRIX["sections"]


def test_all_64_original_sections_are_mapped():
    ids = [s["id"] for s in SECTIONS]
    assert sorted(ids) == list(range(1, 65)), f"missing or duplicated: {ids}"


def test_every_section_has_a_title_and_status():
    valid = {"both", "code", "prompt", "tests", "strengthened", "gap"}
    for s in SECTIONS:
        assert s.get("title"), f"§{s['id']} has no title"
        assert s.get("status") in valid, f"§{s['id']} status {s.get('status')!r} invalid"


def test_every_section_points_somewhere():
    """A mapped section must reference at least one concrete artefact."""
    for s in SECTIONS:
        refs = any(s.get(k) for k in ("prompt", "code", "tests", "scenarios", "config"))
        assert refs or s.get("note"), f"§{s['id']} has no references and no note"


@pytest.mark.parametrize("kind", ["prompt", "code", "tests", "scenarios", "config"])
def test_every_reference_resolves(kind):
    checker = vc.CHECKERS[kind]
    broken = []
    for s in SECTIONS:
        for ref in s.get(kind, []) or []:
            ok, detail = checker(ref)
            if not ok:
                broken.append(f"§{s['id']} {ref}: {detail}")
    for add in MATRIX.get("additions", []):
        for ref in add.get(kind, []) or []:
            ok, detail = checker(ref)
            if not ok:
                broken.append(f"[addition] {ref}: {detail}")
    assert not broken, "unresolvable references:\n" + "\n".join(broken)


def test_all_20_mandated_scenarios_are_covered():
    """§63 of the original lists exactly 20 behaviours that must be tested."""
    sec63 = next(s for s in SECTIONS if s["id"] == 63)
    mandated = sec63["mandated_20"]
    assert sorted(int(k) for k in mandated) == list(range(1, 21))

    missing = []
    for num, entry in mandated.items():
        assert entry.get("scenario"), f"#{num} has no scenario description"
        assert entry.get("tests"), f"#{num} maps to no tests"
        for tfn in entry["tests"]:
            if tfn not in vc.TEST_FUNCS:
                missing.append(f"#{num} {entry['scenario']}: {tfn}")
    assert not missing, "mandated tests missing:\n" + "\n".join(missing)


def test_mandated_scenario_count_is_exactly_twenty():
    sec63 = next(s for s in SECTIONS if s["id"] == 63)
    assert len(sec63["mandated_20"]) == 20


def test_gaps_are_explicitly_flagged_with_a_note():
    """Any section not fully implemented must explain itself."""
    for s in SECTIONS:
        if s["status"] == "gap":
            assert s.get("note"), f"§{s['id']} is a gap with no explanation"


def test_known_gap_is_the_truncated_section_64():
    """The only permitted gap is the truncated tail of the supplied prompt.

    If this test fails, a NEW gap has appeared — investigate before shipping.
    """
    gaps = [s["id"] for s in SECTIONS if s["status"] == "gap"]
    assert gaps == [64], f"unexpected gaps: {gaps}"


def test_additions_are_real_and_justified():
    """v2 additions must exist in code/prompt AND carry a rationale."""
    for add in MATRIX.get("additions", []):
        assert add.get("why"), f"addition {add.get('title')!r} has no rationale"
        refs = any(add.get(k) for k in ("prompt", "code", "tests", "config"))
        assert refs, f"addition {add.get('title')!r} references nothing"


def test_verifier_exits_clean(capsys):
    assert vc.verify(verbose=False) == 0
    out = capsys.readouterr().out
    assert "ALL CLAIMS VERIFIED" in out


def test_coverage_matrix_mentions_every_hard_rule():
    """The four absolute disqualifiers must each be traceable."""
    text = yaml.safe_dump(MATRIX)
    for rule in ("Agricultural", "documents", "INCOME", "TENURE", "75"):
        assert rule.lower() in text.lower(), f"matrix does not mention {rule!r}"
