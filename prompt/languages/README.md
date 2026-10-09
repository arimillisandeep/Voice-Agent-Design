# LANGUAGE SUPPORT MATRIX

> The master prompt (`prompt/system_prompt.md`) is language-agnostic. One overlay file per language
> is appended at render time. **Business rules never change with language** — only wording, register,
> number formatting and grammatical gender.

## Supported

| `language_to_speak` | `language_code` | Overlay | Script | Gender marking | Voice guidance |
|---|---|---|---|---|---|
| English | `en-IN` | *(none — base prompt)* | Latin | none | Indian English accent variant |
| Hindi | `hi-IN` | `hi.md` | Devanagari | **Strong** — verb forms `-ता/-ती`, `-ा हूँ/-ी हूँ` | Native Hindi voice required |
| Marathi | `mr-IN` | `mr.md` | Devanagari | **Strong** — `-तो/-ती` endings | Native Marathi voice; use `कोटी` not `करोड़` |
| Gujarati | `gu-IN` | `gu.md` | Gujarati | **Strong** — `-તો હતો/-તી હતી` | Native Gujarati voice |
| Telugu | `te-IN` | `te.md` | Telugu | Moderate — predicate nouns `-డిని/-రాలిని`; prefer neutral | `-గారు` respect markers mandatory |
| Tamil | `ta-IN` | `ta.md` | Tamil | **Weak** — 1st-person verbs are neutral; avoid gendered nouns | Neutral self-description recommended |
| Kannada | `kn-IN` | `kn.md` | Kannada | Weak — only self-describing nouns differ | Neutral self-description recommended |
| Bengali | `bn-IN` | `bn.md` | Bengali | **None** on verbs; nouns only | Fully neutral; use `টাকা`, `লক্ষ`, `কোটি` |

## Adding a language

1. Copy `hi.md` as the template into `prompt/languages/<code>.md`.
2. Fill in: register, gender table, number conventions, the ~25 standard lines, TTS notes.
3. Add the row above and to `config/languages.yaml`.
4. Re-render: `python tools/render_prompts.py`.
5. Verify with `tests/test_languages.py` (asserts every overlay defines all required lines).

## Gender handling by language family — why the table above matters

The original prompt said *"use forms appropriate to the configured agent gender"* without saying how.
That fails in production two ways: a model applies Hindi-style gender marking to Tamil (producing
ungrammatical output), or it ignores gender entirely in Hindi (producing an agent whose voice is
female but who says `कर रहा हूँ`). The rule per language:

- **Strong gender languages (hi, mr, gu):** gender must appear on first-person verbs. Provide the
  full conjugation table in the overlay so the model copies rather than infers.
- **Moderate (te):** gendered predicate nouns exist; recommend a neutral fallback sentence.
- **Weak / none (ta, kn, bn, en):** instruct the model to use **gender-neutral self-description**.
  Do not force a gendered form — that is what produces unnatural output.

Set `agent_gender` to match the *selected TTS voice*, not the other way round.

## Number formatting

Every language uses the **Indian numbering system** (lakh / crore). Two rules that break TTS:

1. Never emit raw digits for amounts — `7500000` may be read "seven five zero zero zero zero zero".
   Always write the amount in words in the target language.
2. Never translate `lakh` → `million`. `1 million` is wrong in every Indian-language context.

| Amount | en-IN | hi-IN | te-IN | bn-IN |
|---|---|---|---|---|
| ₹75,00,000 | seventy-five lakh rupees | पचहत्तर लाख रुपये | డెబ్భై ఐదు లక్షల రూపాయలు | পঁচাত্তর লক্ষ টাকা |
| ₹1,00,00,000 | one crore rupees | एक करोड़ रुपये | ఒక కోటి రూపాయలు | এক কোটি টাকা |

## Code-switching policy

- The agent speaks the configured language only.
- It may **repeat** an English finance term the customer used (EMI, balance transfer, bank, loan).
- It must **not** switch whole sentences to English, and must not answer in English because the
  customer said one English word.
- If the customer genuinely switches language and stays there, mirror them (§11 of the master prompt)
  — routing and eligibility are unaffected.
