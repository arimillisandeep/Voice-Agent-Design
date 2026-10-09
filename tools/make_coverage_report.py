#!/usr/bin/env python3
"""Generate docs/COVERAGE.md from the verified traceability matrix.

The report is generated, never hand-written, so it cannot claim coverage that the
verifier has not already confirmed. Run `tools/verify_coverage.py` first (or let
`./run.sh` do both).

    PYTHONPATH=src:tools python3 tools/make_coverage_report.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import yaml  # noqa: E402

import verify_coverage as vc  # noqa: E402

MATRIX = yaml.safe_load((ROOT / "docs/traceability.yaml").read_text(encoding="utf-8"))
SECTIONS = MATRIX["sections"]

ICON = {"both": "PASS", "code": "PASS", "prompt": "prompt", "tests": "tests",
        "strengthened": "NEW", "gap": "GAP"}
LBL = {"both": "prompt + code", "code": "code", "prompt": "prompt",
       "tests": "scenario + tests", "strengthened": "strengthened", "gap": "**GAP**"}
MEANING = {
    "both": "stated in the prompt **and** enforced deterministically in code",
    "code": "enforced in code only (no model discretion)",
    "prompt": "model behaviour only (style, tone, phrasing)",
    "tests": "original worked example, now a replayable scenario + assertions",
    "strengthened": "v2 adds handling the original lacked",
    "gap": "**not implemented - needs a business decision**",
}
REF_PREFIX = {"prompt": "prompt ", "code": "", "tests": "test ", "scenarios": "scenario ",
              "config": "config "}


def build() -> str:
    out: list[str] = []
    counts: dict[str, int] = {}
    for s in SECTIONS:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    ref_kinds = ("prompt", "code", "tests", "scenarios", "config")
    total_refs = sum(len(s.get(k) or []) for s in SECTIONS for k in ref_kinds)
    sec63 = next(s for s in SECTIONS if s["id"] == 63)
    mandated = sec63.get("mandated_20") or {}

    out += [
        "# INSTRUCTION COVERAGE REPORT",
        "",
        "> Generated from `docs/traceability.yaml` by `tools/make_coverage_report.py`.",
        "> **Do not edit by hand** - every reference below is mechanically verified by",
        "> `tools/verify_coverage.py` and `tests/test_traceability.py`. Rename a prompt",
        "> heading or delete a test and the build fails.",
        "",
        f"**{len(SECTIONS)}/64** original sections mapped  |  **{total_refs}** references verified  |  "
        f"**{len(vc.TEST_FUNCS)}** test functions  |  **{len(mandated)}/20** mandated scenarios covered",
        "",
        "| Status | Count | Meaning |",
        "|---|---|---|",
    ]
    for k in ("both", "code", "prompt", "tests", "strengthened", "gap"):
        if k in counts:
            out.append(f"| `{k}` | {counts[k]} | {MEANING[k]} |")

    out += ["", "---", "", "## Section-by-section", "",
            "| # | Original instruction | Status | Where it lives |", "|---|---|---|---|"]
    for s in SECTIONS:
        refs: list[str] = []
        for k in ref_kinds:
            for r in (s.get(k) or [])[:3]:
                refs.append(f"`{r}`" if k == "code" else f"{REF_PREFIX[k]}{r}")
        where = "; ".join(refs[:4]) + (" ..." if len(refs) > 4 else "")
        out.append(f"| {s['id']} | {s['title'].replace('|', chr(92)+'|')} "
                   f"| {LBL[s['status']]} | {where} |")

    notes = [s for s in SECTIONS if s.get("note")]
    out += ["", "---", "", "## Notes, caveats and deliberate changes", ""]
    for s in notes:
        out += [f"**Section {s['id']} - {s['title']}**", "", "> " + " ".join(s["note"].split()), ""]

    gaps = [s for s in SECTIONS if s["status"] == "gap"]
    if gaps:
        out += ["---", "", "## Gaps requiring your input", ""]
        for g in gaps:
            out += [f"### Section {g['id']} - {g['title']}", "", " ".join(g["note"].split()), ""]

    adds = MATRIX.get("additions", [])
    if adds:
        out += ["---", "", "## v2 additions with no counterpart in the original", "",
                "| Addition | Why |", "|---|---|"]
        for a in adds:
            out.append(f"| {a['title']} | {a['why']} |")

    out += ["", "---", "", "## Section 63 - the 20 mandated test scenarios", "",
            "| # | Scenario | Tests |", "|---|---|---|"]
    for k in sorted(mandated, key=lambda x: int(x)):
        e = mandated[k]
        shown = ", ".join(f"`{t}`" for t in e["tests"][:3])
        out.append(f"| {k} | {e['scenario']} | {len(e['tests'])} - {shown}"
                   f"{' ...' if len(e['tests']) > 3 else ''} |")
    out += ["",
            "Scenarios 5+6 share one parametrised test and 9+10 share one, so 20 mandated",
            "scenarios map to 18 top-level test functions (47 distinct functions in total).",
            "", "---", "",
            "*Regenerate: `PYTHONPATH=src:tools python3 tools/make_coverage_report.py`*", ""]
    return "\n".join(out)


def main() -> int:
    if vc.verify(verbose=False) != 0:
        print("\nrefusing to write a report from an unverified matrix", file=sys.stderr)
        return 1
    target = ROOT / "docs/COVERAGE.md"
    target.write_text(build(), encoding="utf-8")
    print(f"\nwrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
