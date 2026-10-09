"""Spoken-language -> structured fact parsing.

Handles the messiness of Indian phone conversations: fillers, approximations,
Hindi/Marathi number words, lakh/crore conventions, month-based tenures and
bundled multi-fact answers.

Everything here is *extraction help* for the LLM tool-call layer, not a
replacement for it: the agent still calls `record_eligibility_fact` with an
already-normalised value. These helpers exist so a backend can normalise
free text (ASR transcripts, CRM notes) and so tests can assert on real phrasing.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #
_INDIAN_UNITS = {
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000, "l": 100_000,
    "लाख": 100_000, "लाखों": 100_000, "लक्ष": 100_000, "லட்சம்": 100_000, "లక్ష": 100_000,
    "crore": 10_000_000, "crores": 10_000_000, "cr": 10_000_000, "cro": 10_000_000,
    "करोड़": 10_000_000, "कोटी": 10_000_000, "కోటి": 10_000_000, "கோடி": 10_000_000,
    "thousand": 1_000, "thousands": 1_000, "k": 1_000, "हज़ार": 1_000, "हजार": 1_000,
    "సహస్రం": 1_000, "ஆயிரம்": 1_000,
}

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "twenty five": 25, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "seventy five": 75, "eighty": 80,
    "ninety": 90, "hundred": 100,
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "सात": 7,
    "आठ": 8, "नौ": 9, "दस": 10, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25,
    "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}

_LAKH_WORDS = "lakh|lakhs|lac|lacs|laakh"
_CRORE_WORDS = "crore|crores|cr|koti"
_THOUSAND_WORDS = "thousand|thousands|k"
_NATIVE_UNITS = (
    "लाख|लाखों|लक्ष|करोड़|कोटी|हज़ार|हजार|"     # hi/mr
    "లక్ష|లక్షలు|కోటి|వేలు|"                    # te
    "லட்சம்|கோடி|ஆயிரம்|"                        # ta
    "ಲಕ್ಷ|ಕೋಟಿ|ಸಾವಿರ|"                          # kn
    "ലക്ഷം|കോടി|ആയിരം|"                          # ml
    "লক্ষ|কোটি|হাজার"                            # bn
)

# A number word or numeral, optionally followed by an Indian scale unit.
# Deliberately does NOT match arbitrary two-word spans — those produced false
# positives ("two minutes" -> an amount) in early testing.
_AMOUNT_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?"
    r"|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s\-](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|hundred|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|एक|दो|तीन|चार|पाँच|पांच|छह|सात|आठ|नौ|दस|ग्यारह|बारह|पंद्रह|बीस|पच्चीस|तीस|चालीस|पचास|साठ|सत्तर|पचहत्तर|अस्सी|नब्बे|सौ"
    r")"
    r"\s*(?P<unit>" + _LAKH_WORDS + "|" + _CRORE_WORDS + "|" + _THOUSAND_WORDS + "|" + _NATIVE_UNITS + r")?",
    re.IGNORECASE,
)


def _word_to_number(text: str) -> Optional[float]:
    """'seventy five' -> 75, 'पचास' -> 50. Returns None when not a number word."""
    t = text.strip().lower()
    if t in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[t])
    # compound english: "twenty five"
    parts = t.replace("-", " ").split()
    if len(parts) == 2 and all(p in _WORD_NUMBERS for p in parts):
        a, b = _WORD_NUMBERS[parts[0]], _WORD_NUMBERS[parts[1]]
        if a in (20, 30, 40, 50, 60, 70, 80, 90) and b < 10:
            return float(a + b)
    return None


# Words that look like scale words but are units of time or quantity. A number
# followed by one of these is NEVER a rupee amount ("two minutes", "5 days").
_NON_AMOUNT_UNITS = frozenset(
    {
        "minute", "minutes", "min", "second", "seconds", "sec", "hour", "hours", "hr",
        "day", "days", "week", "weeks", "month", "months", "year", "years", "yr", "yrs",
        "time", "times", "question", "questions", "people", "floor", "floors", "room",
        "rooms", "percent", "percentage", "installment", "installments", "emi", "emis",
        "per", "of", "ago",
        "\u092e\u093f\u0928\u091f", "\u0918\u0902\u091f\u0947", "\u0926\u093f\u0928", "\u0938\u093e\u0932", "\u0935\u0930\u094d\u0937",
        "\u092e\u0939\u0940\u0928\u0947", "\u092c\u093e\u0930",
        "\u0c28\u0c3f\u0c2e\u0c3f\u0c37\u0c3e\u0c32\u0c41", "\u0c30\u0c4b\u0c1c\u0c41\u0c32\u0c41", "\u0c28\u0c46\u0c32\u0c32\u0c41", "\u0c38\u0c02\u0c35\u0c24\u0c4d\u0c38\u0c30\u0c3e\u0c32\u0c41",
        "\u0ba8\u0bbf\u0bae\u0bbf\u0b9f\u0bae\u0bcd", "\u0ba8\u0bbe\u0b9f\u0bcd\u0b95\u0bb3\u0bcd", "\u0bae\u0bbe\u0ba4\u0bae\u0bcd", "\u0b86\u0ba3\u0bcd\u0b9f\u0bc1",
        "\u0ca8\u0cbf\u0cae\u0cbf\u0cb7", "\u0ca6\u0cbf\u0ca8", "\u0ca4\u0cbf\u0c82\u0c97\u0cb3\u0cc1", "\u0cb5\u0cb0\u0ccd\u0cb7",
        "\u0d2e\u0d3f\u0d28\u0d3f\u0d31\u0d4d\u0d31\u0d4d", "\u0d26\u0d3f\u0d35\u0d38\u0d02", "\u0d2e\u0d3e\u0d38\u0d02", "\u0d35\u0d7c\u0d37\u0d02",
        "\u09ae\u09bf\u09a8\u09bf\u099f", "\u09a6\u09bf\u09a8", "\u09ae\u09be\u09b8", "\u09ac\u099b\u09b0",
    }
)


# Digit-grouping patterns. Indian grouping ends in a 3-digit group preceded by 2-digit
# groups (60,00,000); ISO grouping is all 3-digit groups (6,000,000). They are mutually
# exclusive once matched against the WHOLE token, which is why classification is done on
# complete numerals rather than with a substring regex (a substring match backtracks and
# silently truncates "60,00,000" to "60,00").
_ISO_GROUPED_RE = re.compile(r"^\d{1,3}(?:,\d{3})+$")
_INDIAN_GROUPED_RE = re.compile(r"^\d{1,2}(?:,\d{2})*,\d{3}$")
_NUMERAL_TOKEN_RE = re.compile(r"(?<![\d.,])\d[\d,]*\d(?![\d,])")


def _expand_grouped(s: str) -> str:
    """Collapse grouped numerals to plain digits, detecting the grouping system per token.

    ``60,00,000`` -> ``6000000`` (Indian) and ``6,000,000`` -> ``6000000`` (ISO).
    Separators outside numerals are untouched, so "two, three" survives unchanged.
    """
    def _fix(m: "re.Match[str]") -> str:
        tok = m.group(0)
        if _ISO_GROUPED_RE.match(tok) or _INDIAN_GROUPED_RE.match(tok):
            return tok.replace(",", "")
        return tok

    return _NUMERAL_TOKEN_RE.sub(_fix, s)


def _prepare_amount_text(text: str) -> str:
    """Normalise a string for amount scanning: currency symbols, 'rs', digit grouping."""
    s = str(text).strip().lower().replace("\u20b9", " ")
    s = re.sub(r"\brs\.?\b", " ", s)
    s = _expand_grouped(s)
    return re.sub(
        r"\b(rupees|rupaye|rupya|\u0930\u0941\u092a\u092f\u0947|\u0930\u0941\u092a\u092f\u093e)\b", " ", s
    )


# A clause separator between two amounts means they are different figures, not the
# additive parts of one number ("worth 75 lakh AND I need 40 lakh" != 1.15 crore).
_CLAUSE_SEP_RE = re.compile(
    r"[,.;:!?\u0964]|"
    r"\b(?:and|but|or|however|while|whereas|also|so|then|lekin|aur|magar|"
    r"\u0914\u0930|\u0932\u0947\u0915\u093f\u0928|\u092a\u0930|\u0c86\u0ca6\u0cb0\u0cc6|\u0cae\u0ca4\u0ccd)\b"
)


def _scan_amount_spans(s: str, default_unit: int = 100_000) -> list[tuple[int, int, int]]:
    """Scan normalised text for rupee amounts, returning ``(value, start, end)`` spans.

    A number followed by a time or quantity word is skipped ("two minutes", "5 days"),
    and a bare numeral >= 1 lakh is read as absolute rupees rather than lakhs.
    """
    hits: list[tuple[int, int, int]] = []
    for m in _AMOUNT_RE.finditer(s):
        raw = m.group("num")
        unit = (m.group("unit") or "").lower()

        # The regex captures only the first word of a "<number> <unit>" phrase, so the
        # following token must be checked explicitly to reject non-monetary quantities.
        following = s[m.end(): m.end() + 24].strip()
        next_word = re.split(r"[\s,.!?;:]", following, maxsplit=1)[0]
        if unit in _NON_AMOUNT_UNITS or (not unit and next_word in _NON_AMOUNT_UNITS):
            continue

        try:
            num = float(raw)
            from_digits = True
        except ValueError:
            num = _word_to_number(raw)
            from_digits = False
        if num is None:
            continue

        scale = _INDIAN_UNITS.get(unit)
        if scale is not None:
            value = int(num * scale)
        elif not unit:
            if from_digits and num >= 100_000:
                value = int(num)
            else:
                value = int(num * default_unit)
                if value < 1000 and default_unit != 1:
                    continue      # stray small number: "page 2", "flat 5"
        else:
            continue              # unknown word in unit position

        hits.append((value, m.start(), m.end()))
    return hits


def _resolve_spans(s: str, hits: list[tuple[int, int, int]]) -> Optional[int]:
    """Collapse scanned amounts to the single figure the customer means.

    Amounts are only *added* when they sit in one uninterrupted number phrase
    ("one crore twenty lakh"). Across a clause boundary they are separate figures,
    so the largest is taken instead.
    """
    if not hits:
        return None
    values = [h[0] for h in hits]
    if len(hits) > 1 and all(a > b for a, b in zip(values, values[1:])):
        additive = all(
            not _CLAUSE_SEP_RE.search(s[prev_end: cur_start])
            for (_, _, prev_end), (_, cur_start, _) in zip(hits, hits[1:])
        )
        if additive:
            return sum(values)
    return max(values)


def _scan_amounts(s: str, default_unit: int = 100_000) -> list[int]:
    """Values only, for callers that need the list rather than a single figure."""
    return [h[0] for h in _scan_amount_spans(s, default_unit)]


def parse_amount(text: str, default_unit: int = 100_000) -> Optional[int]:
    """Parse a spoken or written rupee amount into an integer number of rupees.

    ``default_unit`` is the multiplier for a *bare* number with no scale word, which in an
    Indian lending conversation means lakhs ("fifty" -> 5000000).

    >>> parse_amount("around fifty lakh")
    5000000
    >>> parse_amount("1.2 crore")
    12000000
    >>> parse_amount("75 lakhs")
    7500000
    >>> parse_amount("fifty")
    5000000
    >>> parse_amount("20 thousand")
    20000
    >>> parse_amount("60,00,000")
    6000000
    >>> parse_amount("two minutes") is None
    True
    >>> parse_amount("one crore twenty lakh")
    12000000
    >>> parse_amount("worth 75,00,000 and I need 40 lakh")
    7500000
    """
    if text is None:
        return None
    s = _prepare_amount_text(text)
    return _resolve_spans(s, _scan_amount_spans(s, default_unit))


def parse_tenure_years(text: str) -> Optional[float]:
    """Parse a repayment period. Accepts years or months.

    >>> parse_tenure_years("ten years")
    10.0
    >>> parse_tenure_years("36 months")
    3.0
    >>> parse_tenure_years("डेढ़ साल")        # 1.5 years
    1.5
    >>> parse_tenure_years("a couple of years") is None
    True
    """
    if text is None:
        return None
    s = str(text).strip().lower()

    m = re.search(r"(\d+(?:\.\d+)?)\s*(year|years|yr|yrs|साल|वर्ष|వర్షాలు|ஆண்டு|ವರ್ಷ)", s)
    if m:
        return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*(month|months|mahine|महीने|महीना|నెలలు|மாதம்)", s)
    if m:
        return round(float(m.group(1)) / 12.0, 2)

    for phrase, val in (("half a year", 0.5), ("डेढ़ साल", 1.5), ("डेढ़ वर्ष", 1.5),
                        ("अढ़ाई साल", 2.5), ("one year", 1.0), ("two year", 2.0),
                        ("three year", 3.0), ("five year", 5.0), ("ten year", 10.0),
                        ("fifteen year", 15.0), ("twenty year", 20.0)):
        if phrase in s:
            return val
    for word, val in _WORD_NUMBERS.items():
        if re.search(rf"\b{re.escape(word)}\b", s) and re.search(
            r"year|years|साल|वर्ष|వర్షాలు|ஆண்டு", s
        ):
            return float(val)
    return None  # ambiguous ("a couple of years", "long term") -> ask again


# --------------------------------------------------------------------------- #
# Categorical facts
# --------------------------------------------------------------------------- #
_PROPERTY_MAP: dict[str, str] = {
    "residential": "residential", "house": "residential", "home": "residential",
    "flat": "residential", "apartment": "residential", "villa": "residential",
    "row house": "residential", "bunglow": "residential", "bungalow": "residential",
    "ghar": "residential", "मकान": "residential", "घर": "residential", "फ्लैट": "residential",
    "అపార్ట్‌మెంట్": "residential", "வீடு": "residential",
    "commercial": "commercial", "shop": "commercial", "showroom": "commercial",
    "office": "commercial", "godown": "commercial", "warehouse": "commercial",
    "complex": "commercial", "दुकान": "commercial", "ऑफिस": "commercial",
    "industrial": "industrial", "factory": "industrial", "unit": "industrial",
    "plant": "industrial", "manufacturing": "industrial", "कारखाना": "industrial",
    "फैक्ट्री": "industrial",
    "agricultural": "agricultural", "agriculture": "agricultural", "farm": "agricultural",
    "farmland": "agricultural", "farm land": "agricultural", "khet": "agricultural",
    "खेत": "agricultural", "कृषि": "agricultural", "खेती": "agricultural",
    "ag land": "agricultural", "agricultural land": "agricultural",
}

_OWNERSHIP_SOLE = ("sole", "solely", "only my name", "only in my name", "my name only",
                   "single owner", "alone", "individual owner", "just me", "only me",
                   "\u092e\u0947\u0930\u0947 \u0928\u093e\u092e", "\u0905\u0915\u0947\u0932\u0947", "\u0905\u0915\u0947\u0932\u0940",
                   "\u0c28\u0c3e \u0c2a\u0c47\u0c30\u0c41\u0c28\u0c77\u0c3f", "\u0ba4\u0ba9\u0bbf\u0baf\u0bbe")
_OWNERSHIP_JOINT = ("joint", "jointly", "co-owner", "co owner", "coowner", "with my wife",
                    "with my husband", "with my brother", "with my sister", "with my father",
                    "with my mother", "with my spouse", "with my son", "with my daughter",
                    "along with", "together with", "partnership", "shared with", "both our names",
                    "two names", "\u0938\u0902\u092f\u0941\u0915\u094d\u0924", "\u0938\u093e\u091d\u093e",
                    "\u0938\u093e\u091d\u0947", "\u092a\u0924\u094d\u0928\u0940 \u0915\u0947 \u0938\u093e\u0925",
                    "\u0c38\u0c02\u0c2f\u0c41\u0c15\u0c4d\u0c24", "\u0b9a\u0bc1\u0b95\u0ba8\u0bcd\u0ba4")

# "<relation> and I own it" / "<relation> ke saath" -> joint, even without the word "joint".
# Includes romanised (Hinglish) forms, because ASR transcripts of Hindi calls are
# frequently returned in Latin script ("mere bhai ke saath").
_RELATIONS = (r"wife|husband|brother|sister|father|mother|son|daughter|spouse|partner|"
              r"biwi|pati|patni|bhai|behen|bahen|pita|pitaji|mata|mummy|beta|beti|"
              r"\u092a\u0924\u094d\u0928\u0940|\u092a\u0924\u093f|\u092d\u093e\u0908|\u092c\u0939\u0928|"
              r"\u092a\u093f\u0924\u093e|\u092e\u093e\u0924\u093e|\u092c\u0947\u091f\u093e|\u092c\u0947\u091f\u0940")
_OWNERSHIP_JOINT_RE = re.compile(
    r"(?:my|mere|\u092e\u0947\u0930\u0947)\s+(?:" + _RELATIONS + r")\s+"
    r"(?:and\s+i|i\s+and|&\s*i|\u0914\u0930\s+\u092e\u0948\u0902)|"
    r"(?:" + _RELATIONS + r")\s+(?:ke\s+saath| tho| உடன்|తో|ಜೊತೆ|സഹിതം|এর\s+সাথে)|"
    r"(?:hum|ham|we)\s+(?:sab|sabh)\s+(?:ke|mile|milkar)",
    re.IGNORECASE,
)

_DOC_YES = ("original", "originals", "yes", "available", "have them", "at home", "in the bank locker",
            "मूल", "ओरिजिनल", "हां", "उपलब्ध")
_DOC_NO = ("photocopy", "photocopies", "xerox", "scan", "scanned", "copy", "copies", "lost",
           "not available", "don't have", "do not have", "no", "missing", "photostat",
           "फोटोकॉपी", "नहीं", "खो गई", "उपलब्ध नहीं")

_OCC_SALARIED = ("salaried", "salary", "employee", "employed", "employment", "job", "works for",
                 "working for", "work for", "work in a company", "company", "government", "govt",
                 "bank", "naukri", "service karta", "service karti", "naukri karta",
                 "naukri karti", "private company", "it company", "teacher", "engineer",
                 "\u0935\u0947\u0924\u0928", "\u0928\u094c\u0915\u0930\u0940", "\u0915\u0930\u094d\u092e\u091a\u093e\u0930\u0940",
                 "\u0909\u0926\u094d\u092f\u094b\u0917", "\u0928\u094b\u0915\u0930\u0940", "\u092a\u0917\u093e\u0930",
                 "\u0c09\u0c26\u0c4d\u0c2f\u0c4b\u0c17\u0c02", "\u0b9a\u0bae\u0bb3\u0bae\u0bcd",
                 "\u0cb8\u0cc7\u0cb5\u0cc6", "\u0d1c\u0d4b\u0d32\u0d3f", "\u099a\u09be\u0995\u09b0\u09bf")
_OCC_SELF = ("self employed", "self-employed", "own business", "my business", "business",
             "entrepreneur", "proprietor", "trader", "shopkeeper", "shop owner", "freelancer",
             "freelance", "professional", "doctor", "ca ", "chartered", "consultant",
             "contractor", "dhanda", "vyapar", "vyavsay", "dukaan",
             "have a shop", "run a shop", "own a shop", "my own shop",
             "have my own", "run my own", "own my own",
             "manufacturing unit", "agency", "commission",
             "\u0935\u094d\u092f\u0935\u0938\u093e\u092f", "\u092c\u093f\u091c\u0928\u0947\u0938",
             "\u0927\u0902\u0927\u093e", "\u0938\u094d\u0935\u0930\u094b\u091c\u0917\u093e\u0930",
             "\u0926\u0941\u0915\u093e\u0928", "\u0935\u094d\u092f\u093e\u092a\u093e\u0930",
             "\u0c35\u0c4d\u0c2f\u0c3e\u0c2a\u0c3e\u0c30\u0c02", "\u0bb5\u0bbf\u0ba9\u0bbf\u0baf\u0bcb\u0b95\u0bae\u0bcd",
             "\u0cb5\u0ccd\u0caf\u0cbe\u0caa\u0cbe\u0cb0", "\u0d35\u0d4d\u0d2f\u0d3e\u0d2a\u0d3e\u0d30\u0d02",
             "\u09ac\u09cd\u09af\u09ac\u09b8\u09be")
_OCC_NONE = ("unemployed", "student", "studying", "retired", "retirement", "no job",
             "not working", "housewife", "homemaker", "between jobs",
             "\u092c\u0947\u0930\u094b\u091c\u0917\u093e\u0930", "\u0938\u0947\u0935\u093e\u0928\u093f\u0935\u0943\u0924\u094d\u0924",
             "\u091b\u093e\u0924\u094d\u0930", "\u0917\u0943\u0939\u093f\u0923\u0940")

_INCOME_BANK = ("bank", "account", "credited", "credit", "neft", "imps", "upi", "transfer",
                "बैंक", "खाते", "खाता", "जमा")
_INCOME_CASH = ("cash", "hard cash", "by hand", "नकद", "कैश", "नगद", "रोकड़")

_YES = ("yes", "yeah", "yep", "sure", "haan", "ha", "ji", "हाँ", "हां", "హౌదు", "ஆம்", "હા", "ho")
_NO = ("no", "nope", "nah", "not really", "nahi", "na", "नहीं", "काదు", "இல்லை", "ના")


def _match_pair(text: str, mapping: dict[str, str]) -> Optional[tuple[str, str]]:
    """Return ``(needle, value)`` for the first dictionary entry found in the text.

    Distinct from :func:`_match`, which returns only the value -- callers that need to
    reason about *which* phrase matched (e.g. to suppress the ambiguous word "home")
    must use this instead.
    """
    s = f" {str(text).strip().lower()} "
    for needle, value in mapping.items():
        if needle in s:
            return needle, value
    return None


def _match(text: str, needles: tuple[str, ...] | list[str] | dict[str, str]) -> Optional[str]:
    s = f" {str(text).strip().lower()} "
    if isinstance(needles, dict):
        for needle, value in needles.items():
            if needle in s:
                return value
        return None
    for needle in needles:
        if needle in s:
            return needle
    return None


# Location/finance phrases containing a property noun that are NOT describing the
# property itself. "the documents are at home" says nothing about property type;
# "home loan" names a product. Without this, both record a false `residential`.
_PROPERTY_FALSE_POSITIVE_RE = re.compile(
    r"\b(?:at|from|in|to|towards|for)\s+(?:my\s+|the\s+|our\s+)?(?:home|house)\b|"
    r"\bhome\s+(?:loan|emi|finance)\b|"
    r"\b(?:stay|living|located)\s+(?:at|in)\s+(?:my\s+|the\s+)?home\b",
    re.IGNORECASE,
)
_AMBIGUOUS_PROPERTY_WORDS = frozenset({"home", "house"})


def parse_property_type(text: str) -> Optional[str]:
    """'my own house' -> residential; 'agricultural land' -> agricultural.

    Returns None when the only property noun appears inside a location or product
    phrase ("documents are at home", "I have a home loan"), which does not describe
    the collateral at all.
    """
    s = str(text).lower()
    pair = _match_pair(s, _PROPERTY_MAP)
    if pair is None:
        return None
    needle, value = pair
    if needle in _AMBIGUOUS_PROPERTY_WORDS:
        # Strip every false-positive phrase; if nothing property-like remains, the
        # sentence was about a location or a product, not the collateral.
        stripped = _PROPERTY_FALSE_POSITIVE_RE.sub(" ", s)
        if _match(stripped, _PROPERTY_MAP) is None:
            return None
    return value


# "Family property" says nothing about whose name is on the title deed, so it must be
# clarified rather than recorded as joint (master prompt 25).
# "my own residential house" implies sole ownership, but only when tied to a property
# noun -- otherwise "I run my own business" would wrongly record sole ownership.
_OWNERSHIP_SOLE_RE = re.compile(
    r"(?:my|our)\s+own\s+(?:\w+\s+){0,2}"
    r"(?:house|home|flat|apartment|property|place|building|shop|office|villa|bunglow|bungalow)|"
    r"(?:it|that|this)\s*(?:is|'s|s)?\s+mine\b|\bi\s+own\s+it\b|\bmine\s+alone\b|"
    r"self[\s-]owned|\bsolo\s+owner\b|"
    r"\u0905\u092a\u0928\u093e\s+\u0918\u0930|\u0905\u092a\u0928\u093e\s+\u092e\u0915\u093e\u0928|"
    r"\u092e\u0947\u0930\u093e\s+\u0916\u0941\u0926\s+\u0915\u093e",
    re.IGNORECASE,
)
_OWNERSHIP_AMBIGUOUS_RE = re.compile(
    r"family\s+property|ancestral|\u092a\u0930\u093f\u0935\u093e\u0930\u093f\u0915\s*\u0938\u0902\u092a\u0924\u094d\u0924\u093f|"
    r"\u092a\u0948\u0924\u0943\u0915|dadaji\s+ki|pitrak",
    re.IGNORECASE,
)


def parse_ownership(text: str) -> Optional[str]:
    """Sole vs joint. Returns None -- never a guess -- when the answer is ambiguous.

    A bare "yes" to "is it solely yours or joint?" is deliberately treated as unknown,
    and "family property" is returned as ``unclear`` so the agent asks one clarifying
    question instead of assuming joint ownership.
    """
    s = str(text).lower()
    joint = _match(s, _OWNERSHIP_JOINT) or _OWNERSHIP_JOINT_RE.search(s)
    sole = _match(s, _OWNERSHIP_SOLE) or _OWNERSHIP_SOLE_RE.search(s)
    if _OWNERSHIP_AMBIGUOUS_RE.search(s) and not (joint or sole):
        return "unclear"
    if joint:
        return "joint"
    if sole:
        return "sole"
    if _match(s, _YES):
        return None           # a bare "yes" to "sole or joint?" is ambiguous
    return None


def parse_yes_no(text: str) -> Optional[str]:
    s = str(text).strip().lower()
    if _match(s, _NO) and not _match(s, _YES):
        return "no"
    if _match(s, _YES):
        return "yes"
    return None


def parse_documents(text: str) -> Optional[str]:
    """Only 'yes' when originals are clearly available; never guess from vagueness."""
    s = str(text).lower()
    if _match(s, _DOC_NO):
        return "no"
    if "original" in s and _match(s, _YES):
        return "yes"
    if "original" in s and not _match(s, ("not", "don't", "do not", "unavailable", "नहीं")):
        return "yes"
    if _match(s, ("somewhere", "not sure", "maybe", "i think", "pata nahi", "शायद", "पता नहीं")):
        return "unclear"
    yn = parse_yes_no(s)
    return yn


def parse_occupation(text: str) -> Optional[str]:
    """Classify work into salaried / self-employed / none.

    Self-employed markers are tested FIRST because "self employed" contains the substring
    "employed"; checking salaried first misclassified it as salaried. The employer nouns
    that caused the opposite error ("bank", "company") are deliberately absent from
    _OCC_SELF, so neither ordering mistake can recur.
    """
    s = str(text).lower()
    if _match(s, _OCC_NONE):
        return "none"
    if _match(s, _OCC_SELF):
        return "self_employed"
    if _match(s, _OCC_SALARIED):
        return "salaried"
    return None


def parse_income_mode(text: str) -> Optional[str]:
    s = str(text).lower()
    bank = _match(s, _INCOME_BANK)
    cash = _match(s, _INCOME_CASH)
    if bank and cash:
        # "mostly cash but some comes to the bank" -> clarify
        if _match(s, ("mostly", "most of", "majority", "mainly", "ज़्यादा", "ज्यादा")):
            dominant_cash = any(
                f"{w} cash" in s or f"cash {w}" in s
                for w in ("mostly", "most", "mainly", "majority")
            )
            return "cash" if dominant_cash else "mixed"
        return "mixed"
    if cash:
        return "cash"
    if bank:
        return "bank"
    return None


# --------------------------------------------------------------------------- #
# Intent detection (routing terminals, master prompt §5)
# --------------------------------------------------------------------------- #
INTENT_PATTERNS: dict[str, tuple[str, ...]] = {
    "busy": ("busy", "in a meeting", "meeting", "driving", "can't talk", "cant talk",
             "cannot talk", "can't speak", "cant speak", "cannot speak", "call me later",
             "call me tomorrow", "call me back", "call back", "not now", "no time",
             "occupied", "have to go", "has to go", "gotta go", "got to go", "must go",
             "in a call", "on another call", "stepping out", "getting late", "running late",
             "not free", "baad mein baat", "abhi nahi", "kaam mein", "time nahi hai",
             "\u092c\u093e\u0939\u0930 \u0939\u0942\u0901", "\u092e\u0940\u091f\u093f\u0902\u0917", "\u0935\u094d\u092f\u0938\u094d\u0924", "\u092c\u093e\u0926 \u092e\u0947\u0902",
             "\u0917\u093e\u0921\u093c\u0940 \u091a\u0932\u093e", "\u0921\u094d\u0930\u093e\u0907\u0935", "\u0905\u092d\u0940 \u0928\u0939\u0940\u0902",
             "\u092b\u0941\u0930\u094d\u0938\u0924 \u0928\u0939\u0940\u0902", "\u091c\u093e\u0928\u093e \u0939\u0948"),
    "decline": ("not interested", "no interest", "don't want", "dont want", "do not want",
                "no thanks", "not required", "मैं नहीं", "रुचि नहीं", "नहीं चाहिए", "कोई ज़रूरत नहीं"),
    "dnc": ("don't call me again", "do not call me", "stop calling", "remove my number",
                "never call", "फोन मत करना", "दोबारा कॉल मत"),
    "end_call": ("bye", "goodbye", "hang up", "keep it", "that's all", "cut the call",
                 "अलविदा", "फोन रख"),
    "existing_loan": ("already have a loan", "existing loan", "have a loan on", "loan running",
                      "loan is going on", "current loan", "मेरे पास पहले से", "पहले से लोन",
                      "लोन चल रहा", "loan चालू"),
    "emi_reduction": ("reduce my emi", "lower my emi", "less emi", "emi kam", "emi reduce",
                      "emi kam karni", "ईएमआई कम", "इएमआई कम"),
    "transfer": ("balance transfer", "transfer my loan", "refinance", "take over my loan",
                 "loan transfer", "बैलेंस ट्रांसफर", "ट्रांसफर कर"),
    "human": ("talk to a person", "speak to a person", "human", "real person", "manager",
              "executive", "आदमी से", "इंसान से"),
    # NOTE: never use a bare "i am not" here — it also matches "I am not interested"
    # and would misroute a decline into the wrong-person terminal.
    "wrong_person": ("wrong number", "wrong person", "no such person", "doesn't live here",
                     "does not live here", "not staying here", "you've got the wrong",
                     "गलत नंबर", "यहाँ कोई नहीं", "ऐसा कोई नहीं"),
    "rate_question": ("interest rate", "rate of interest", "what is the rate", "roi",
                      "ब्याज दर", "कितना ब्याज", "interest kitna"),
}


def detect_intents(text: str) -> list[str]:
    """Return every routing intent present in the utterance (order preserved)."""
    s = f" {str(text).lower()} "
    found = [name for name, needles in INTENT_PATTERNS.items() if _match(s, needles)]
    return found


# --------------------------------------------------------------------------- #
# Bundled-answer extraction
# --------------------------------------------------------------------------- #
# Multilingual cue words for the two amount contexts. Kept as regex alternations so
# they can be dropped straight into the clause-scoped patterns below.
_VALUE_WORDS = (
    "कीमत|क़ीमत|मूल्य|"                 # hi
    "किंमत|मूल्य|"                       # mr
    "કિંમત|મૂલ્ય|"                       # gu
    "విలువ|ధర|"                          # te
    "மதிப்பு|விலை|"                      # ta
    "ಮೌಲ್ಯ|ಬೆಲೆ|"                        # kn
    "മൂല്യം|വില|"                        # ml
    "মূল্য|দাম"                           # bn
)
_BORROW_WORDS = (
    "चाहिए|ज़रूरत|जरूरत|लोन|"             # hi
    "हवे|गरज|कर्ज|"                       # mr
    "જોઈએ|જરૂર|લોન|"                     # gu
    "కావాలి|అవసరం|రుణం|"                  # te
    "தேவை|வேண்டும்|கடன்|"                  # ta
    "ಬೇಕು|ಅಗತ್ಯ|ಸಾಲ|"                     # kn
    "വേണം|ആവശ്യം|വായ്പ|"                   # ml
    "দরকার|চাই|ঋণ"                        # bn
)
_DOC_WORDS = (
    "कागज|दस्तावेज़|दस्तावेज|"            # hi
    "कागदपत्रे|"                          # mr
    "કાગળ|દસ્તાવેજ|"                     # gu
    "పత్రాలు|కాగితాలు|"                   # te
    "ஆவணம்|ஆவணங்கள்|"                     # ta
    "ದಾಖಲೆ|ಕಾಗದ|"                        # kn
    "രേഖ|രേഖകൾ|കടലാസ്|"                  # ml
    "নথি|কাগজ|দলিল"                       # bn
)

_VALUE_CTX_RE = re.compile(
    r"(?:worth|value|valuation|market\s*value|" + _VALUE_WORDS + r")\s*(?:of)?\D{0,25}?",
    re.IGNORECASE,
)
_BORROW_CTX_RE = re.compile(
    r"(?:borrow|need|require|want|looking\s+(?:for|to)|take\s+a\s+loan|loan\s+of|"
    r"sanction|apply\s+for|" + _BORROW_WORDS + r")\s*\D{0,25}?",
    re.IGNORECASE,
)
_DOC_CTX_RE = re.compile(
    # "original(s)" counts as document context on its own: customers routinely answer
    # "yes the originals are available" without saying the word "documents".
    # Negative phrasings (photocopy/xerox/scan) must match too, otherwise a "no" answer
    # is never seen as a documents answer at all.
    r"(?:documents?|papers?|originals?|photocop(?:y|ies)|photostat|xerox|scans?|"
    r"copies|title\s*deed|kaagaz|orig\s+docs|" + _DOC_WORDS + r"|"
    r"\u0921\u0949\u0915\u094d\u092f\u0941\u092e\u0947\u0902\u091f|\u0913\u0930\u093f\u091c\u093f\u0928\u0932|\u092e\u0942\u0932|"
    r"\u092b\u094b\u091f\u094b\u0915\u0949\u092a\u0940)",
    re.IGNORECASE,
)


def _amount_in(text: str, ctx_re: "re.Pattern[str]", default_unit: int = 100_000) -> Optional[int]:
    """Extract the rupee amount appearing in the first clause that matches ``ctx_re``."""
    m = ctx_re.search(text)
    if not m:
        return None
    return parse_amount(text[m.end(): m.end() + 45], default_unit=default_unit)


def _all_amounts(text: str, default_unit: int = 100_000) -> list[int]:
    """Every plausible rupee amount in the utterance, in order of appearance.

    Shares the scanner with :func:`parse_amount` so digit grouping and the
    time/quantity guard behave identically on both paths.
    """
    return _scan_amounts(_prepare_amount_text(text), default_unit)


def extract_facts(text: str, *, amount_default_unit: int = 100_000) -> dict[str, Any]:
    """Best-effort extraction of every fact present in one utterance (master prompt 11/12).

    Returns only keys it is confident about; anything absent stays UNKNOWN and the agent
    must ask for it. Deliberately conservative -- it never guesses (master prompt 14).

    Amounts are disambiguated by clause context, so
    "worth about one crore ... I need fifty lakh" yields market_value=1cr and
    loan_amount=50L instead of collapsing both into one field.
    """
    if not text:
        return {}
    facts: dict[str, Any] = {}
    s = str(text)
    low = s.lower()

    prop = parse_property_type(low)
    if prop:
        facts["property_type"] = prop

    own = parse_ownership(low)
    if own:
        facts["ownership_status"] = own

    occ = parse_occupation(low)
    if occ:
        facts["occupation"] = occ

    inc = parse_income_mode(low)
    if inc:
        facts["income_mode"] = inc

    tenure = parse_tenure_years(low)
    if tenure is not None:
        facts["tenure_years"] = tenure

    if _DOC_CTX_RE.search(low):
        docs = parse_documents(s)
        if docs:
            facts["documents_original"] = docs

    mv = _amount_in(low, _VALUE_CTX_RE)
    la = _amount_in(low, _BORROW_CTX_RE, default_unit=amount_default_unit)

    if mv is None and la is None:
        # No explicit context. One amount = what they want to borrow;
        # two amounts read naturally as "worth X, need Y" (larger = value).
        amounts = _all_amounts(s, default_unit=amount_default_unit)
        if len(amounts) == 1:
            la = amounts[0]
        elif len(amounts) >= 2:
            mv, la = max(amounts), min(amounts)

    if mv:
        facts["market_value"] = mv
    if la:
        facts["loan_amount"] = la

    return facts


# --------------------------------------------------------------------------- #
# Callback time
# --------------------------------------------------------------------------- #
_DAYPARTS = (
    r"morning|afternoon|evening|night|noon|late\s+evening|early\s+morning|"
    r"\u0938\u0941\u092c\u0939|\u0926\u094b\u092a\u0939\u0930|\u0936\u093e\u092e|\u0930\u093e\u0924|"
    r"\u0c09\u0c26\u0c2f\u0c02|\u0c38\u0c02\u0c1c\u0c47|\u0ba4\u0bbf\u0b95\u0bb4\u0bcd|\u0bae\u0bbe\u0bb2\u0bc8"
)
_RELDAYS = (
    r"today|tonight|tomorrow|day\s+after\s+tomorrow|next\s+week|this\s+weekend|weekend|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"aaj|kal|parson|parsoun|hafte\s+mein|is\s+weekend|"   # romanised Hindi
    r"somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar|"
    r"\u0906\u091c|\u0915\u0932|\u092a\u0930\u0938\u094b\u0902|\u0939\u092b\u093c\u094d\u0924\u0947|"
    r"\u0c30\u0c47\u0c2a\u0c41|\u0c28\u0c47\u0c21\u0c41|\u0ba8\u0bbe\u0bb3\u0bc8|\u0b87\u0ba9\u0bcd\u0bb1\u0bc1"
)
_CLOCK_RE = re.compile(
    r"(?:at\s+|around\s+|by\s+|near\s+|\u092c\u091c\u0947\s*)?"
    r"(\d{1,2})(?:\s*[:.]\s*(\d{2}))?\s*"
    r"(am|pm|a\.m\.|p\.m\.|\u092c\u091c\u0947|baje)?",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(r"(\d+)\s*(minute|minutes|min|hour|hours|hr)", re.IGNORECASE)


def parse_callback_time(text: str, *, now_hour: Optional[int] = None) -> Optional[str]:
    """Normalise a spoken callback preference to a short canonical phrase.

    The customer's own wording is preserved where possible; this function exists so the
    value stored in state is consistent and so an ambiguous answer can be detected and
    re-asked rather than silently recorded.

    >>> parse_callback_time("Tomorrow around 11")
    'tomorrow 11'
    >>> parse_callback_time("call me in the evening")
    'evening'
    >>> parse_callback_time("after 30 minutes")
    'in 30 minutes'
    >>> parse_callback_time("kal subah 10 baje")
    'kal 10'
    >>> parse_callback_time("later") is None
    True
    """
    if not text:
        return None
    s = str(text).strip().lower()
    s = re.sub(r"\b(call\s+me|callback|call\s+back|phone\s+me|contact\s+me|reach\s+me|"
               r"\u092b\u094b\u0928|\u0915\u0949\u0932)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,!?")

    if not s or s in {"later", "some time", "sometime", "kabhi", "baad mein",
                      "\u092c\u093e\u0926 \u092e\u0947\u0902", "anytime", "any time"}:
        return None                       # ambiguous -> agent must ask again

    dur = _DURATION_RE.search(s)
    if dur:
        unit = dur.group(2).rstrip("s")
        if unit == "min":
            unit = "minute"
        plural = "s" if int(dur.group(1)) != 1 else ""
        return f"in {dur.group(1)} {unit}{plural}"

    day = re.search(_RELDAYS, s)
    part = re.search(_DAYPARTS, s)
    clock = _CLOCK_RE.search(s)

    pieces: list[str] = []
    if day:
        pieces.append(day.group(0))
    if part:
        pieces.append(part.group(0))
    if clock and clock.group(1):
        hour = int(clock.group(1))
        minute = clock.group(2)
        mer = (clock.group(3) or "").replace(".", "").replace("\u092c\u091c\u0947", "baje")
        # A bare number is only a time if it is plausible and anchored by context,
        # so "I need 50 lakh" never becomes a 50 o'clock callback.
        plausible = 1 <= hour <= 12
        anchored = bool(mer) or bool(day) or bool(part)
        if plausible and anchored:
            when = f"{hour}:{minute}" if minute else str(hour)
            if mer and mer != "baje":
                when += f" {mer}"
            pieces.append(when)

    if not pieces:
        return None
    return " ".join(dict.fromkeys(pieces))   # dedupe, keep order


def classify_utterance(text: str) -> dict[str, Any]:
    """Return every routing intent and every extractable fact in one utterance.

    When the utterance carries no busy/decline intent it is treated as an answer to the
    callback question, so a bare "tomorrow around 11" still yields a callback time.
    """
    intents = detect_intents(text)
    facts = extract_facts(text)
    if not facts and not intents:
        cb = parse_callback_time(text)
        if cb:
            facts["callback_time"] = cb
    return {"intents": intents, "facts": facts}
