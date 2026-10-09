#!/usr/bin/env python3
"""Render per-locale system prompts from the master prompt + language overlays.

Usage:
    python tools/render_prompts.py                 # render every locale into prompt/rendered/
    python tools/render_prompts.py --locale hi-IN  # one locale
    python tools/render_prompts.py --check         # CI: fail if rendered output is stale
    python tools/render_prompts.py --stdout hi-IN  # print to stdout (paste into Retell/Vapi)

Also substitutes the call-time variables with values from `config/sample_context.yaml`
when `--demo` is passed, so you can eyeball exactly what the model receives.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIR = ROOT / "prompt"
OUT_DIR = PROMPT_DIR / "rendered"

sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from homecredit_lap.rules import MAX_LOAN_AMOUNT  # noqa: E402
from homecredit_lap.state import MIN_TENURE_YEARS, MAX_TENURE_YEARS  # noqa: E402


def format_indian(amount: int) -> str:
    """Group digits the Indian way: 7500000 -> 75,00,000 (last group 3, then pairs).

    The prompt is read by Indian customers and Indian TTS voices, so ISO grouping
    (7,500,000) would be read aloud incorrectly.
    """
    s = str(amount)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def load_languages() -> list[dict]:
    cfg = yaml.safe_load((ROOT / "config/languages.yaml").read_text(encoding="utf-8"))
    return cfg["languages"]


def _inject_runtime_facts(base: str, lang: dict) -> str:
    """Prepend the resolved numeric limits so the prompt and code can never disagree."""
    header = (
        "<!-- Rendered from prompt/system_prompt.md"
        + (f" + prompt/languages/{lang['overlay']}" if lang["overlay"] else "")
        + f" for {lang['code']} by tools/render_prompts.py. Do not edit directly. -->\n\n"
    )
    limits = (
        "## 0. RESOLVED LIMITS (generated from config/product_rules.yaml)\n\n"
        f"- Maximum loan amount: **\u20b9{format_indian(MAX_LOAN_AMOUNT)}**"
        f" ({lang['max_75_lakh_words']})\n"
        f"- Repayment tenure: **{MIN_TENURE_YEARS} to {MAX_TENURE_YEARS} years**, inclusive\n"
        f"- Currency word: **{lang['currency_word']}**\n"
        f"- Scale words: **{lang['lakh_crore_terms']['lakh']} / {lang['lakh_crore_terms']['crore']}**\n"
        f"- Agent gender marking: **{lang['gender_marking']}**\n"
        f"- Output script: **{lang['script']}**\n\n"
        "---\n\n"
    )
    return header + limits + base


def render(locale: str | None = None, demo_context: dict | None = None) -> dict[str, str]:
    """Return {locale_code: rendered_prompt} for one or all locales."""
    base = (PROMPT_DIR / "system_prompt.md").read_text(encoding="utf-8")
    out: dict[str, str] = {}

    for lang in load_languages():
        if locale and lang["code"] != locale:
            continue
        text = _inject_runtime_facts(base, lang)
        if lang["overlay"]:
            overlay = (PROMPT_DIR / "languages" / lang["overlay"]).read_text(encoding="utf-8")
            text += "\n\n---\n\n" + overlay
        if demo_context:
            for key, value in demo_context.items():
                text = text.replace("{{" + key + "}}", str(value))
        out[lang["code"]] = text
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--locale", help="render a single locale, e.g. hi-IN")
    ap.add_argument("--check", action="store_true",
                    help="fail if prompt/rendered/ is stale (for CI)")
    ap.add_argument("--stdout", metavar="LOCALE", help="print one locale to stdout")
    ap.add_argument("--demo", action="store_true",
                    help="substitute variables from config/sample_context.yaml")
    args = ap.parse_args()

    demo_context = None
    if args.demo:
        path = ROOT / "config/sample_context.yaml"
        if path.exists():
            demo_context = yaml.safe_load(path.read_text(encoding="utf-8"))

    if args.stdout:
        rendered = render(args.stdout, demo_context)
        if not rendered:
            print(f"unknown locale: {args.stdout}", file=sys.stderr)
            return 2
        sys.stdout.write(rendered[args.stdout])
        return 0

    rendered = render(args.locale, demo_context)
    if not rendered:
        print("no locales matched", file=sys.stderr)
        return 2

    if args.check:
        stale = []
        for code, text in rendered.items():
            target = OUT_DIR / f"{code}.md"
            if not target.exists() or target.read_text(encoding="utf-8") != text:
                stale.append(code)
        if stale:
            print("STALE rendered prompts: " + ", ".join(stale), file=sys.stderr)
            print("run: python tools/render_prompts.py", file=sys.stderr)
            return 1
        print(f"OK — {len(rendered)} rendered prompts are up to date")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for code, text in rendered.items():
        target = OUT_DIR / f"{code}.md"
        target.write_text(text, encoding="utf-8")
        print(f"  wrote {target.relative_to(ROOT)}  ({len(text):,} chars)")
    print(f"rendered {len(rendered)} locale(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
