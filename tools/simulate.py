#!/usr/bin/env python3
"""Drive the LAP agent's decision engine from the terminal.

Two modes:

    python tools/simulate.py --scenario scenarios/qualified.yaml   # replay a script
    python tools/simulate.py --interactive                          # type customer replies

This exercises the same code path a Retell/Vapi webhook uses: utterance -> parse ->
state -> deterministic rules -> next action. No LLM call is made, so it is free,
offline and repeatable -- it tells you what the engine will instruct the model to do.

In interactive mode press Enter on an empty line to accept the extractor's guess, or
type `fact key=value` to force a normalised value (e.g. `fact tenure_years=12`),
or `state` / `lead` / `quit`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from homecredit_lap.runtime import CallSession  # noqa: E402

CYAN, GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[36m", "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"
)


def _colour(action: str) -> str:
    return {
        "submit": GREEN, "transfer": YELLOW, "schedule_callback": YELLOW,
        "end_call": RED, "offer_cap": YELLOW, "clarify": CYAN,
    }.get(action, DIM)


def show(result, *, verbose: bool = False) -> None:
    colour = _colour(result.action)
    if result.intents:
        print(f"   {DIM}intents: {', '.join(result.intents)}{RESET}")
    if result.recorded:
        print(f"   {DIM}recorded: {', '.join(result.recorded)}{RESET}")
    print(f"   {colour}[{result.action}]{RESET} {result.say or '(no line supplied)'}")
    if result.next_item and not result.end_call:
        print(f"   {DIM}next checklist item: {result.next_item}{RESET}")
    if result.end_call:
        print(f"   {BOLD}{colour}TERMINAL: {result.terminal}"
              f" | lead_status: {result.lead_status}{RESET}")
    if verbose:
        print(f"   {DIM}missing: {result.missing_items or 'none'}{RESET}")


def run_scenario(path: Path, *, verbose: bool = False) -> int:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    session = CallSession(
        customer_name=data.get("customer_name", "the customer"),
        language=data.get("language", "en-IN"),
        agent_name=data.get("agent_name", "Priya"),
        company_name=data.get("company_name", "Home Credit"),
    )
    print(f"\n{BOLD}{data.get('name', path.stem)}{RESET}")
    if data.get("description"):
        print(f"{DIM}{data['description']}{RESET}")
    print("-" * 78)

    for turn in data.get("turns", []):
        text = turn.get("customer", "")
        facts = turn.get("facts")
        print(f"{CYAN}customer:{RESET} {text}")
        result = session.handle(text, facts=facts)
        show(result, verbose=verbose)
        if result.end_call:
            remaining = data.get("turns", [])[data["turns"].index(turn) + 1:]
            if remaining:
                print(f"   {DIM}(call ended; {len(remaining)} scripted turn(s) not reached){RESET}")
            break

    expected = data.get("expect", {})
    print("-" * 78)
    failures = []
    for key, want in expected.items():
        got = session.lead_payload().get(key)
        ok = got == want
        failures.append((key, want, got)) if not ok else None
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"   {mark} expect {key} = {want!r}" + ("" if ok else f", got {got!r}"))
    if verbose:
        print(f"\n{DIM}lead payload:{RESET}")
        print(json.dumps(session.lead_payload(), indent=2, ensure_ascii=False, default=str))
    print()
    return 1 if failures else 0


def interactive(*, language: str, customer: str, verbose: bool) -> None:
    session = CallSession(customer_name=customer, language=language)
    print(f"{BOLD}LAP agent simulator — interactive{RESET}  (language={language})")
    print(f"{DIM}Enter customer replies. Commands: 'fact key=value', 'state', 'lead', 'quit'{RESET}")
    print(f"{DIM}Empty line + Enter accepts the extractor's own reading of your last input.{RESET}\n")

    while True:
        try:
            raw = input(f"{CYAN}customer>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not raw:
            continue
        if raw.lower() in {"quit", "exit", "q"}:
            break
        if raw.lower() == "state":
            print(json.dumps(session.state.to_dict(), indent=2, ensure_ascii=False, default=str))
            continue
        if raw.lower() == "lead":
            payload = session.lead_payload()
            payload.pop("transcript", None)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            continue
        if raw.lower().startswith("fact "):
            body = raw[5:].strip()
            if "=" not in body:
                print(f"{RED}usage: fact key=value{RESET}")
                continue
            key, _, value = body.partition("=")
            value = value.strip()
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = value
            result = session.handle("", facts={key.strip(): parsed})
            print(f"   {DIM}forced {key.strip()}={parsed!r}{RESET}")
            show(result, verbose=verbose)
        else:
            result = session.handle(raw)
            show(result, verbose=verbose)

        if session.state.terminal:
            print(f"\n{BOLD}Call finished: {session.state.terminal}{RESET}")
            print(json.dumps({k: v for k, v in session.lead_payload().items()
                              if k not in ("transcript", "audit_trail")},
                             indent=2, ensure_ascii=False, default=str))
            break


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--scenario", type=Path, nargs="*", help="scenario YAML file(s) to replay")
    group.add_argument("--all-scenarios", action="store_true", help="replay every file in scenarios/")
    group.add_argument("--interactive", "-i", action="store_true", help="drive a call by typing")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--language", default="en-IN")
    ap.add_argument("--customer", default="Rajesh Kumar")
    args = ap.parse_args()

    if args.interactive:
        interactive(language=args.language, customer=args.customer, verbose=args.verbose)
        return 0

    paths = list(args.scenario or [])
    if args.all_scenarios:
        paths += sorted((ROOT / "scenarios").glob("*.yaml"))
    if not paths:
        print("no scenarios found", file=sys.stderr)
        return 2

    failed = 0
    for path in paths:
        if not path.exists():
            print(f"{RED}missing scenario: {path}{RESET}", file=sys.stderr)
            failed += 1
            continue
        failed += run_scenario(path, verbose=args.verbose)
    total = len(paths)
    print(f"{BOLD}{total - failed}/{total} scenario(s) behaved as expected{RESET}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
