# CHANGELOG — original prompt → v2.0

Every change from the supplied 64-section master prompt, with rationale. Grouped as
**structural**, **behavioural fixes**, **bugs found while building**, and **open questions**.

Nothing here silently changes a business rule. Where a rule was ambiguous or incomplete, it is
listed under *Open questions* rather than guessed.

---

## 1. Structural changes

### 1.1 Eligibility logic moved out of the prompt into code

**Before:** the prompt contained the ₹75 lakh cap, the 3–15 year window, the four-row
occupation × income decision table, and the 11-condition handoff gate — all as prose the LLM had to
hold in working memory and apply correctly on every turn.

**After:** `src/homecredit_lap/rules.py::evaluate()` is the single decision function. The LLM's only
job is to report what it heard; the tool response tells it what to say and whether the call ends.

**Why:** threshold arithmetic and multi-condition gates are exactly what LLMs get wrong
intermittently, and the failure is silent — a loan above the cap gets qualified, or a 2-year tenure
passes. In code it is testable (291 tests) and cannot drift with model version or temperature.

### 1.2 64 sections → 16 sections + 2 appendices

The original repeated the same instructions several times (the disqualification rule appears in
§24, §26, §29, §32, §34, §53, §54, §57, §61, §64; the "never invent criteria" rule in §20, §35, §37,
§38). Repetition in a long prompt does not improve compliance — it dilutes attention and inflates
token cost on every single turn of every call.

Each rule now appears **once**, in the section where the agent needs it, with a routing table (§5)
that replaces the five overlapping priority lists (§10, §34, §50, §51, §64).

### 1.3 Worked examples moved out of the prompt

§52–§62 were 11 scripted dialogues embedded in the system prompt. They are now
`scenarios/*.yaml` — replayable by `tools/simulate.py` and asserted by `tests/test_scenarios.py`.

**Why:** examples in a prompt are *hoped* to be followed; examples in a test suite are *verified*.
The same content now does double duty as documentation and as regression protection.

### 1.4 Single source of truth for numbers

`config/product_rules.yaml` holds every threshold. `tools/render_prompts.py` generates a
"RESOLVED LIMITS" header into each rendered prompt from the same constants the code uses.
`tests/test_config_sync.py` fails if YAML, Python and prompt text disagree.

**Why:** the original hardcoded `₹75,00,000` in nine separate places. Changing the cap meant finding
all nine — miss one and the agent quotes a different number than the one it enforces.

---

## 2. Behavioural fixes (gaps in the original)

### 2.1 The original prompt was truncated mid-sentence

Section 64 ended at "Income → Cash" with no completion, and there was no §65+. The supplied text
appears cut off. **The absolute-rules section is incomplete as provided.** Reconstructed in §14 +
Appendix A from the earlier sections; please confirm nothing was lost.

### 2.2 "Occupation + Income Mode" counted as one item but holds two facts

§9 lists it as item 5 of 7. The original never said what happens if the customer answers only one
half. Now explicit (§6): one natural question turn may cover both, but the item is not satisfied
until both facts are known. `CallState.answered("occupation_and_income")` enforces it.

### 2.3 No handling for a customer who owns no property

The original assumed the customer always has a property. "I don't own any property, I want to buy
one" would fall through every rule. Added `property_type = none` → disqualify with a distinct line.

### 2.4 No handling for unemployed / student / retired

§28 said "Do not disqualify self-employed customers" but never covered *no* income source.
Added `occupation = none` → disqualify. **This is a new rule — confirm it matches business intent**
(see Open questions).

### 2.5 No re-ask limit

§7 said "listen completely" and §36/§51 said "return to the first missing item", but nothing stopped
an infinite loop with an uncooperative customer. Added `MAX_REASKS = 2` in `runtime.py`: after two
unanswered attempts the item is marked unresolved and the agent moves on or closes politely.

### 2.6 Silence / no-answer handling was absent

Now covered by the re-ask limit above, and the item is recorded in `clarifications_pending` so the
CRM shows which facts were never obtained.

### 2.7 Callback time was captured but never validated

§42 said "capture accurately" and "politely clarify if ambiguous" but gave no rule for what counts as
ambiguous. `parse_callback_time` returns `None` for "later", "anytime", "some time" — which keeps the
call in the callback branch instead of storing a useless preference. **A time is never invented.**

### 2.8 DNC handling had no mechanism

§43 said "respect the request" but nothing recorded it. Added `mark_do_not_call` tool + `dnc`
terminal + `lead_status: "dnc"` so the suppression actually reaches the CRM.

### 2.9 AI-disclosure question was unhandled

§45 covered "can I speak to a person" but not "are you a robot?". Given Indian regulatory direction
on synthetic voice, added §8.6: answer honestly, never impersonate a human.

### 2.10 Compliance section added

The original had no OTP/PIN/Aadhaar guard, no "never misrepresent as a bank officer" rule, and no
explicit consent framing for an **outbound** call. Added to §14. For an unsolicited outbound lending
call in India this is the highest-risk gap in the original.

### 2.11 Routing priority consolidated

§10, §34, §50, §51 and §64 each stated a priority order, and they disagreed in edge cases
(§50 put "customer wants to end the call" first; §34 put disqualification first). Now one table
(§5), implemented as one ordered function, and tested for the conflicting cases
(`test_22`: DNC beats transfer; `test_23`: transfer beats busy; `test_24`: disqualification beats
collection).

### 2.12 "Family property" clarified rather than assumed

§25 said "Clarify if actual ownership is unclear" but gave no value for it. Added
`ownership_status = "unclear"` → one clarifying question. Previously the agent had no way to record
"asked but not resolved".

### 2.13 Mixed income added

§29 forced a binary bank/cash. "Some cash, some bank" is extremely common with self-employed
customers. Added `income_mode = "mixed"` → one clarifying question, which then resolves to bank
(continue) or cash (disqualify). Without this the agent had to guess — violating §14.

---

## 3. Bugs found and fixed while building

These were caught by tests, not by reading. Each is a regression test now.

| # | Bug | Impact | Fix |
|---|---|---|---|
| 1 | `"60,00,000"` parsed as ₹600,00,00,000 | Cap check would wrongly trigger on a written amount | Per-token Indian vs ISO grouping classifier |
| 2 | `"repay over two years"` yielded a ₹2,00,000 loan | Tenure answer recorded as an amount | Time/quantity unit guard in the amount scanner |
| 3 | `"worth 75 lakh and I need 40 lakh"` summed to 1.15 crore | Additive rule ("one crore twenty lakh") fired across clauses | Span-adjacency check before summing |
| 4 | `"I am not interested"` matched the wrong-person rule | A decline misrouted to the wrong-person terminal | Removed the over-broad `"i am not"` pattern |
| 5 | `"I run my own business"` implied **sole ownership** | A work answer recorded as a property-title fact | Sole-ownership regex scoped to property nouns |
| 6 | `"I'm employed with a bank"` → self-employed | Occupation misclassified (dict-order bug) | Salaried markers tested before self-employed |
| 7 | `documents_original="yes"` coerced to boolean `True` | Disqualification check `== "no"` silently never fired | Key-aware coercion (bool keys vs enum keys) |
| 8 | Session released before `submit_eligibility_facts` ran | Qualified leads never handed off; `handoff_completed=False` | `submit` action is non-terminal until the tool runs |
| 9 | Disqualification reported `lead_status="in_progress"` to CRM | Lost leads looked like abandoned calls | Terminal persisted on the record path |
| 10 | `"family property"` auto-recorded as joint | Assumed a fact the customer never stated | Returns `unclear` → clarifying question |
| 11 | Busy intent missed `"I have to go"`, `"call me tomorrow"` | Busy customers kept being qualified | Broadened the busy pattern list |
| 12 | Cap acceptance didn't rewrite the amount on the runtime path | CRM received an out-of-policy ₹90 lakh figure | Cap normalisation centralised in `CallState.record` |

Bug 7 and 9 are worth emphasising: both are **silent** failures. The agent would have sounded
perfect on a call recording while writing wrong data to the CRM.

---

## 4. Deliberately preserved

Unchanged from the original, because they were correct:

- The 7-item checklist and its logical order.
- All four hard disqualifiers: agricultural property, no original documents, cash income,
  tenure outside 3–15 years.
- ₹75 lakh cap with the offer-then-confirm negotiation (never an auto-reject).
- Joint ownership is always eligible.
- **No minimum property value, no LTV, no credit score, no income floor.** §31 and §35 were explicit
  that none exist; `test_26`/`test_27` now lock that in so nobody adds one later.
- Transfer routing for existing loans / EMI reduction.
- "Preliminary check" language; never "approved" or "guaranteed".
- Latest-answer-wins for corrections; contradictions get one clarification.
- Wrong person → zero disclosure.

---

## 5. Open questions for the business

Points where the original was silent and I chose the conservative reading. **Each should be
confirmed before production.**

1. **Freelancers / gig workers.** §28 said "determine whether platform rules classify them as
   self-employed; if unclear, clarify." I treat freelancer → self-employed (eligible). Confirm.
2. **No income source.** Unemployed/student/retired now disqualifies (`occupation = none`). The
   original never covered this. A retired customer with rental income is arguably eligible.
3. **Market value far below the loan request.** No LTV rule exists, so a ₹50 lakh request against a
   ₹10 lakh property currently **qualifies**. Correct per §31/§35, but likely unintended commercially.
4. **Tenure in months.** "36 months" → 3 years (eligible). "30 months" → 2.5 years (disqualified).
   Confirm no rounding tolerance is wanted.
5. **Callback resolution.** The customer's own words are stored verbatim ("tomorrow around 11").
   Does your dialer need an ISO-8601 timestamp instead? The tool accepts `resolved_iso` if so.
6. **Human escalation.** §45 assumed no warm transfer. If your platform supports it, `transfer_lead`
   already takes `specialist="senior_loan_expert"` — say the word and I'll wire the warm-transfer path.
7. **Wrong-person disclosure.** §17 permits naming the customer to a third party. That is a privacy
   judgement call; the current line reveals the name and nothing else.
8. **The truncated §64.** Please re-send the tail of the original so I can confirm nothing was lost.
