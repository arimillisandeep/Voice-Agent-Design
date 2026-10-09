# Home Credit — LAP Outbound Voice Agent (v2.0)

A refined, production-ready rebuild of the Loan Against Property pre-qualification voice agent.

**The core change:** the original was a 64-section prose document that asked the LLM to remember
thresholds, do arithmetic, and enforce routing priority all at once. This version keeps the prompt
short and moves every deterministic rule into code, so eligibility cannot drift with model behaviour.

```
LLM  →  "customer said: residential, joint, cash income"     (reporting only)
code →  evaluate() → disqualify, reason=cash_income, say=…   (deciding)
```

---

## Quick start

```bash
cd homecredit-lap-agent
python3 -m pip install -r requirements.txt

./run.sh              # verify everything, then start the demo server on :8080
./run.sh --check      # verify only (tests + doctests + scenarios + render sync)
./run.sh --serve      # skip verification, just serve
PORT=9000 ./run.sh    # serve on a different port
```

`run.sh` refuses to start the server if any check fails — override with `--serve`.
It runs 7 checks: dependencies, tests, doctests, scenarios, render sync,
**traceability**, and coverage-report regeneration.

Individual commands:

```bash
PYTHONPATH=src python3 -m pytest tests/ -q                  # 291 tests, no network
PYTHONPATH=src python3 -m doctest src/homecredit_lap/parsing.py -v
PYTHONPATH=src python3 tools/simulate.py --all-scenarios    # 12 scripted calls
PYTHONPATH=src python3 tools/simulate.py --interactive      # drive a call yourself
PYTHONPATH=src python3 tools/render_prompts.py --stdout hi-IN
python3 server/app.py --port 8080                           # webhook server
```

### The browser demo

`GET /` serves an interactive UI (`server/demo.html`, inline assets only). Type a customer
reply or click one of the 12 scenario buttons; the side panel shows the live 7-item
checklist, the terminal state, and the exact CRM lead payload.

**No LLM is called.** Your text goes through `parsing.py` → `CallState` → `rules.evaluate()` —
the same deterministic path a Retell/Vapi webhook hits. That makes it free, offline and
repeatable, but it also means the demo uses regex extraction where production uses the model's
normalised `record_eligibility_fact` calls. An occasional miss in the demo is a parser
limitation, not a rule-engine bug.

Endpoints: `GET /` · `POST /chat` · `POST /reset` · `POST /retell/tool/<name>` ·
`POST /vapi/tool/<name>` · `GET /health`

---

## Layout

```
prompt/
  system_prompt.md          # the refined master prompt (paste into Retell/Vapi)
  languages/                # per-locale overlays + support matrix
    README.md               # which languages mark gender, and how
    hi.md mr.md gu.md te.md ta.md kn.md bn.md
  rendered/                 # generated: master + overlay + resolved limits
config/
  product_rules.yaml        # single source of truth for every threshold
  state_schema.yaml         # per-call state contract
  languages.yaml            # locale registry
  sample_context.yaml       # demo values for {{variables}}
src/homecredit_lap/
  state.py                  # CallState + checklist order + numeric limits
  rules.py                  # evaluate(): routing priority, disqualifiers, closing lines
  parsing.py                # spoken text -> facts (amounts, tenure, intents, 8 languages)
  tools.py                  # the tool layer the LLM calls
  runtime.py                # CallSession: utterance -> action, with re-ask limiting
server/app.py               # stdlib webhook server (Retell + Vapi payload shapes)
platforms/
  retell.tools.json         # tool declarations for Retell
  vapi.tools.json           # tool declarations for Vapi
docs/
  traceability.yaml         # all 64 original sections -> where each now lives
  COVERAGE.md               # generated report (do not hand-edit)
tools/
  render_prompts.py         # master + overlay -> per-locale prompt
  simulate.py               # CLI simulator (scenario replay + interactive)
  verify_coverage.py        # mechanically checks every claim in the matrix
  make_coverage_report.py   # regenerates docs/COVERAGE.md
scenarios/*.yaml            # 12 replayable call scripts with expected outcomes
tests/                      # 291 tests
CHANGELOG.md                # every change from the original, with rationale
```

---

## What the engine guarantees

| Rule | Enforced in | Test |
|---|---|---|
| Agricultural property → disqualify | `rules._disqualifier` | `test_02*` |
| Original documents unavailable → disqualify | `rules._disqualifier` | `test_04*` |
| Cash income → disqualify (both occupations) | `rules._disqualifier` | `test_03*` |
| Tenure outside 3–15 years → disqualify | `rules._disqualifier` | `test_05_06*` |
| Above ₹75 lakh → offer the cap, never auto-reject | `rules.evaluate` | `test_07*` |
| Cap accepted → amount rewritten to exactly 75,00,000 | `CallState.record` | `test_07b` |
| Joint ownership never disqualifies | `rules._disqualifier` | `test_08*` |
| Existing loan / EMI reduction → transfer specialist | `rules.evaluate` (priority 3) | `test_09_10*` |
| Busy → capture callback, never invent a time | `rules.evaluate` (priority 4) | `test_11*` |
| No minimum property value / LTV / credit score invented | `config` + prompt §14 | `test_26`, `test_27` |
| Wrong person → zero disclosure | `rules.evaluate` (priority 2) | `test_21` |
| Never re-ask a captured item | `CallState.missing_items` | `test_12b`, `test_12c` |
| Never say "approved" / "guaranteed" | `rules.SAY["qualified"]` | `test_01b` |

Routing priority is a single ordered function, so "I'm busy but I want to reduce my EMI"
resolves the same way every time (transfer, priority 3 over 4) — `test_23`.

---

## Multi-language

Eight locales render from one master prompt plus a per-language overlay. Business rules are
identical in all of them; only wording, number formatting and gender marking change.

| Locale | Script | Gender marking |
|---|---|---|
| `en-IN` | Latin | none |
| `hi-IN` | Devanagari | **strong** — verb forms differ |
| `mr-IN` | Devanagari | **strong** |
| `gu-IN` | Gujarati | **strong** |
| `te-IN` | Telugu | moderate |
| `ta-IN` | Tamil | weak |
| `kn-IN` | Kannada | weak |
| `bn-IN` | Bengali | none on verbs |

Two details that break Indian-language voice agents in production, both handled here:

1. **Number formatting.** Amounts are always emitted as words in the target language using
   lakh/crore (`पचहत्तर लाख`, `డెబ్భై ఐదు లక్షల`), never digits — TTS reads `7500000`
   digit-by-digit. Never `million`.
2. **Gender concordance.** Strong-gender languages get an explicit conjugation table in the overlay
   so the model copies forms rather than inferring them. Weak/none languages are told to use
   gender-neutral self-description, because forcing a gendered form there produces unnatural output.

See `prompt/languages/README.md`.

---

## Deploying

**Retell**
1. Paste `prompt/rendered/<locale>.md` into the agent's System Prompt.
2. Add the tools from `platforms/retell.tools.json`.
3. Point each custom tool's webhook at `POST https://YOUR-HOST/retell/tool/<name>`.
4. Inject `customer_name`, `company_name`, `agent_name`, `agent_gender`, `language_code` as call
   variables (see `config/sample_context.yaml`).

**Vapi**
1. Same prompt. Tools from `platforms/vapi.tools.json`; set each `server.url`.
2. Put the variables in `assistantOverrides.variableValues`.
3. Keep `maxTokens` around 200 and `temperature` 0.2–0.4 — long outputs break the
   one-question-per-turn rule and raise latency.

**State.** `server/app.py` keeps per-call state in memory. For multi-instance deployments swap
`InMemoryStore` for Redis keyed on `call_id`; the rest of the server is unchanged.

---

## Instruction coverage

`docs/traceability.yaml` maps **all 64 sections** of the original master prompt to where each
instruction now lives — prompt heading, code symbol, config key, test function, scenario file.

It is not a hand-written claim. `tools/verify_coverage.py` resolves every reference:

```
OK  all 64 original sections mapped (64 entries, 64 unique)
OK  350/350 references resolve (prompt headings, code symbols, tests, scenarios, config keys)
OK  §63 mandated scenarios: 20/20 mapped, 47 distinct test functions, 0 missing
```

`tests/test_traceability.py` runs the same checks under pytest, so renaming a prompt heading or
deleting a test breaks the build rather than silently invalidating the report.
`tests/test_traceability.py::test_known_gap_is_the_truncated_section_64` asserts the **only**
permitted gap is §64 — if a new gap ever appears, that test fails.

Read `docs/COVERAGE.md` for the full section-by-section table.

## Changing a business rule

Edit `config/product_rules.yaml`, then mirror it in `src/homecredit_lap/rules.py` (or
`state.py` for the numeric limits). `tests/test_config_sync.py` fails if the YAML, the Python
constants and the prompt text disagree — so a cap change cannot reach production half-applied.

Then re-render: `python tools/render_prompts.py`. The rendered prompt's "RESOLVED LIMITS" header is
generated from the same constants the code uses.
