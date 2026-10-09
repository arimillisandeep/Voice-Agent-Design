#!/usr/bin/env python3
"""Verify docs/traceability.yaml against reality.

Every claim in the matrix is checked mechanically:

* `prompt`    -> the heading exists in prompt/system_prompt.md
* `code`      -> the symbol imports and is callable/defined
* `tests`     -> the test function exists in tests/
* `scenarios` -> the YAML file exists in scenarios/
* `config`    -> the key path resolves in the named config file
* `sections`  -> all 64 original sections are present exactly once

So the coverage report cannot rot: delete a test or rename a prompt heading and
this fails.

    python tools/verify_coverage.py            # human-readable report
    python tools/verify_coverage.py --strict   # exit 1 on any broken reference
"""

from __future__ import annotations

import argparse
import importlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

PROMPT = (ROOT / "prompt/system_prompt.md").read_text(encoding="utf-8")
MATRIX = yaml.safe_load((ROOT / "docs/traceability.yaml").read_text(encoding="utf-8"))

TEST_FILES = list((ROOT / "tests").glob("test_*.py"))
TEST_FUNCS: set[str] = set()
for f in TEST_FILES:
    TEST_FUNCS |= set(re.findall(r"^def (test_\w+)", f.read_text(encoding="utf-8"), re.M))

SCENARIO_FILES = {p.name for p in (ROOT / "scenarios").glob("*.yaml")}

PROMPT_HEADINGS = re.findall(r"^## (.+)$", PROMPT, re.M)

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m")

EXPECTED_SECTIONS = 64


# --------------------------------------------------------------------------- #
def norm_heading(h: str) -> str:
    return re.sub(r"\s+", " ", h).strip().lower()


NORMALISED_HEADINGS = {norm_heading(h): h for h in PROMPT_HEADINGS}


def check_prompt(ref: str) -> tuple[bool, str]:
    """A prompt ref matches a heading, or is literal text present in the prompt."""
    if norm_heading(ref) in NORMALISED_HEADINGS:
        return True, f"heading '{NORMALISED_HEADINGS[norm_heading(ref)]}'"
    # Allow short-form refs like "APPENDIX A" or "9. THE ₹75 LAKH CAP"
    for h in PROMPT_HEADINGS:
        if norm_heading(ref) in norm_heading(h) or norm_heading(h).startswith(norm_heading(ref)):
            return True, f"heading '{h}'"
    if ref in PROMPT:
        return True, "literal text present"
    return False, "no matching heading or literal text"


def check_code(ref: str) -> tuple[bool, str]:
    """Resolve 'module.path.Symbol' or 'module.path.Class.attr'."""
    parts = ref.split(".")
    for split in range(len(parts) - 1, 0, -1):
        mod_path, sym_path = ".".join(parts[:split]), parts[split:]
        try:
            obj = importlib.import_module(mod_path)
        except ImportError:
            continue
        try:
            for attr in sym_path:
                obj = getattr(obj, attr)
            return True, f"{mod_path}.{ '.'.join(sym_path) }"
        except AttributeError:
            return False, f"module {mod_path} imports but has no attribute '{sym_path[0]}'"
    return False, f"cannot import any module prefix of {ref!r}"


def check_test(ref: str) -> tuple[bool, str]:
    if ref in TEST_FUNCS:
        return True, "defined"
    close = [t for t in TEST_FUNCS if ref.split("_")[1][:4] in t]
    return False, ("not found" + (f" (did you mean one of {sorted(close)[:3]}?)" if close else ""))


def check_scenario(ref: str) -> tuple[bool, str]:
    if ref in SCENARIO_FILES:
        return True, "exists"
    return False, f"scenarios/{ref} does not exist"


def check_config(ref: str) -> tuple[bool, str]:
    """Resolve 'file.yaml:key' or 'file.yaml:top.sub.leaf'."""
    if ":" not in ref:
        return False, "expected 'file.yaml:keypath'"
    fname, keypath = ref.split(":", 1)
    path = ROOT / "config" / fname
    if not path.exists():
        return False, f"config/{fname} does not exist"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    node = data
    for part in keypath.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return False, f"config/{fname} has no key path {keypath!r} (stops at {part!r})"
    return True, f"config/{fname}:{keypath}"


CHECKERS = {
    "prompt": check_prompt,
    "code": check_code,
    "tests": check_test,
    "scenarios": check_scenario,
    "config": check_config,
}


# --------------------------------------------------------------------------- #
def verify(verbose: bool = False) -> int:
    sections = MATRIX["sections"]
    ids = [s["id"] for s in sections]

    print(f"{BOLD}TRACEABILITY VERIFICATION{RESET}")
    print(f"{DIM}original master prompt -> v2.0 implementation{RESET}\n")

    problems: list[str] = []

    # -- 1. every original section is mapped exactly once --------------------
    missing = [i for i in range(1, EXPECTED_SECTIONS + 1) if i not in ids]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    extra = [i for i in ids if i < 1 or i > EXPECTED_SECTIONS]
    if missing:
        problems.append(f"original sections not mapped: {missing}")
    if dupes:
        problems.append(f"sections mapped more than once: {dupes}")
    if extra:
        problems.append(f"out-of-range section ids: {extra}")
    status = f"{GREEN}OK{RESET}" if not (missing or dupes or extra) else f"{RED}FAIL{RESET}"
    print(f"  {status}  all {EXPECTED_SECTIONS} original sections mapped "
          f"({len(ids)} entries, {len(set(ids))} unique)")

    # -- 2. every reference resolves ----------------------------------------
    total_refs = 0
    total_refs_seen: set[str] = set()
    broken: list[str] = []
    for sec in sections:
        for kind, checker in CHECKERS.items():
            for ref in sec.get(kind, []) or []:
                total_refs += 1
                ok, detail = checker(ref)
                if not ok:
                    broken.append(f"§{sec['id']} {kind}: {ref} -> {detail}")
                elif verbose:
                    print(f"    {DIM}ok §{sec['id']:>2} {kind:9} {ref} ({detail}){RESET}")
    for add in MATRIX.get("additions", []):
        for kind, checker in CHECKERS.items():
            for ref in add.get(kind, []) or []:
                total_refs += 1
                ok, detail = checker(ref)
                if not ok:
                    broken.append(f"[addition] {add['title']} {kind}: {ref} -> {detail}")

    status = f"{GREEN}OK{RESET}" if not broken else f"{RED}FAIL{RESET}"
    print(f"  {status}  {total_refs - len(broken)}/{total_refs} references resolve "
          f"(prompt headings, code symbols, tests, scenarios, config keys)")
    for b in broken:
        problems.append(b)
        print(f"        {RED}x{RESET} {b}")

    # -- 3. status summary ---------------------------------------------------
    counts: dict[str, int] = {}
    for sec in sections:
        counts[sec["status"]] = counts.get(sec["status"], 0) + 1
    print()
    print(f"  {BOLD}coverage by status{RESET}")
    for k in ("both", "code", "prompt", "tests", "strengthened", "gap"):
        if k in counts:
            colour = RED if k == "gap" else GREEN if k in ("both", "code") else YELLOW
            print(f"    {colour}{k:14}{RESET} {counts[k]:>3}  "
                  f"{DIM}{'prompt + enforced in code' if k=='both' else 'enforced in code only' if k=='code' else 'model behaviour only' if k=='prompt' else 'now a scenario + assertions' if k=='tests' else 'v2 adds handling the original lacked' if k=='strengthened' else 'NOT implemented'}{RESET}")

    # -- 4. the 20 mandated test scenarios (§63) -----------------------------
    sec63 = next(s for s in sections if s["id"] == 63)
    mandated = sec63.get("mandated_20") or {}
    nums = sorted(int(k) for k in mandated)
    missing_nums = [i for i in range(1, 21) if i not in nums]
    unresolved: list[str] = []
    for k, entry in mandated.items():
        for tfn in entry.get("tests", []):
            if tfn not in TEST_FUNCS:
                unresolved.append(f"#{k} {entry.get('scenario')}: {tfn}")
            total_refs_seen.add(tfn)
    ok = not missing_nums and not unresolved
    status = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
    print(f"\n  {status}  §63 mandated scenarios: {len(nums)}/20 mapped, "
          f"{len(total_refs_seen)} distinct test functions, {len(unresolved)} missing")
    if missing_nums:
        problems.append(f"§63 mandated scenarios not mapped: {missing_nums}")
    for u in unresolved:
        problems.append(f"§63 mandated test missing -> {u}")
    if verbose:
        for k in nums:
            e = mandated[k]
            print(f"        {DIM}#{k:>2} {e.get('scenario','')[:42]:44} "
                  f"{len(e.get('tests',[]))} test(s){RESET}")

    # -- 5. gaps requiring a business decision -------------------------------
    gaps = [s for s in sections if s["status"] == "gap"]
    if gaps:
        print(f"\n  {RED}{BOLD}GAPS REQUIRING YOUR INPUT{RESET}")
        for g in gaps:
            print(f"    §{g['id']} {g['title']}")
            for line in (g.get("note") or "").split("\n"):
                if line.strip():
                    print(f"        {DIM}{line.strip()}{RESET}")

    print()
    if problems:
        print(f"  {RED}{BOLD}{len(problems)} PROBLEM(S) FOUND{RESET}")
        return 1
    print(f"  {GREEN}{BOLD}ALL CLAIMS VERIFIED{RESET} — every mapped instruction resolves to "
          f"real prompt text, code, tests or config")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="alias for the default behaviour")
    ap.add_argument("--verbose", "-v", action="store_true", help="list every resolved reference")
    args = ap.parse_args()
    rc = verify(args.verbose)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
