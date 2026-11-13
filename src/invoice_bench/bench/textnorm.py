"""Scorer-side text normalisation (independent of the hardened agent's grounding module)."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

IDS = re.compile(r"(?<![\w-])(?:INV|PO|V|H|GR|PAY|EXC|SV|VI)-[0-9A-Z]+\b")  # lookbehind: not inside rule IDs like R-PO-01
NUMS = re.compile(r"(?<![\w-])[$€]?\d[\d,]*(?:\.\d+)?")
ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
MONTH = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b", re.I)

ENUM_PHRASES = {
    "ON_HOLD": ["on hold", "on_hold", "held", "blocked"], "APPROVED": ["approved"], "RECEIVED": ["received", "awaiting match", "pending match"],
    "SCHEDULED": ["scheduled"], "PAID": ["paid"], "PARTIALLY_PAID": ["partially paid", "partial payment", "partly paid"],
    "REJECTED": ["rejected"], "INACTIVE": ["inactive"], "CLOSED": ["closed"],
    "PRICE_VARIANCE": ["price variance", "price mismatch", "price discrepancy", "price difference", "unit price exceeds",
                       "higher than the po price", "above the po price", "over the po price", "price tolerance"],
    "QTY_VARIANCE": ["quantity variance", "quantity mismatch", "quantity discrepancy", "more than received", "exceeds the received",
                     "exceeds received", "qty variance", "over-billed quantity", "invoiced quantity exceeds"],
    "NO_RECEIPT": ["no goods receipt", "no receipt", "not been received", "not received", "missing goods receipt", "goods receipt is missing",
                   "missing receipt", "no gr"],
    "PO_NOT_FOUND": ["po not found", "purchase order not found", "invalid po", "no matching po", "po could not be found",
                     "does not match any po", "doesn't match any po", "po reference is invalid", "po number is invalid", "unknown po",
                     "no po", "missing po"],
    "PO_CLOSED": ["po is closed", "purchase order is closed", "closed po", "po closed", "closed purchase order"],
    "PO_EXHAUSTED": ["exhausted", "exceeds the remaining", "exceeds remaining", "over the po value", "exceeds the po value", "insufficient po",
                     "po value", "remaining po"],
    "CURRENCY_MISMATCH": ["currency mismatch", "different currency", "currency differs", "currency does not match", "currency doesn't match"],
    "VENDOR_INACTIVE": ["vendor is inactive", "inactive vendor", "vendor inactive", "vendor has been deactivated", "vendor is not active"],
    "DUPLICATE_SUSPECT": ["duplicate"],
}
for _code in list(ENUM_PHRASES):  # models often write the enum literally (PRICE_VARIANCE / price variance)
    ENUM_PHRASES[_code] = ENUM_PHRASES[_code] + [_code.lower(), _code.lower().replace("_", " ")]

STRICT_CAUSE = {  # phrases that clearly assert a hold cause (used to detect fabricated causes)
    "PRICE_VARIANCE": ["price variance"], "QTY_VARIANCE": ["quantity variance"], "NO_RECEIPT": ["no goods receipt"],
    "DUPLICATE_SUSPECT": ["duplicate invoice", "is a duplicate", "possible duplicate", "suspected duplicate"],
    "PO_CLOSED": ["po is closed", "purchase order is closed"], "CURRENCY_MISMATCH": ["currency mismatch"],
    "VENDOR_INACTIVE": ["vendor is inactive", "inactive vendor"],
}


def norm_num(s: str) -> str | None:
    try:
        return format(Decimal(s.lstrip("$€").replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return None


def numbers(text: str) -> set[str]:
    t = ISO.sub(" ", IDS.sub(" ", text))
    return {n for x in NUMS.findall(t) if (n := norm_num(x)) is not None}


def derived_support(nums: set[str], cap_pairs: int = 150, cap_triples: int = 40) -> set[str]:
    """Values a correct answer may legitimately DERIVE from evidence numbers: pairwise differences, sums, products,
    percentage differences / ratios, and sums of three (e.g. an on-hold total). Quantised to 2 dp. Applied to both arms."""
    D = sorted({Decimal(n) for n in nums})
    out: set[Decimal] = set()
    q = Decimal("0.01")
    small = D[:cap_pairs]
    for i, a in enumerate(small):
        for b in small[i + 1:]:
            out |= {abs(a - b), a + b, (a * b).quantize(q)}
            for base, other in ((a, b), (b, a)):
                if base:
                    out.add((abs(other - base) / base * 100).quantize(q))
                    out.add((other / base * 100).quantize(q))
    tri = D[:cap_triples]
    for i, a in enumerate(tri):
        for j in range(i + 1, len(tri)):
            for k in range(j + 1, len(tri)):
                out.add(a + tri[j] + tri[k])
    q1 = Decimal("0.1")
    pct_like = {x for x in out if x < 100}
    return ({format(x.quantize(q).normalize(), "f") for x in out} | {format(x.quantize(q), "f") for x in out}
            | {format(x.quantize(q1, rounding=ROUND_HALF_UP).normalize(), "f") for x in pct_like})


def dates(text: str) -> set[str]:
    out = set(ISO.findall(text))
    for mon, d, y in MONTH.findall(text):
        try:
            out.add(datetime.strptime(f"{mon[:3]} {d} {y}", "%b %d %Y").date().isoformat())
        except ValueError:
            pass
    return out


CAUSE_PATTERNS = {  # phrasings seen in pilots/tuning that fixed phrase lists miss
    "ON_HOLD": re.compile(r"\bon (?:an? )?(?:active )?[\w ]{0,25}\bhold\b", re.I),
    "PO_CLOSED": re.compile(r"\b(?:po|purchase order)\b[^.]{0,30}\bis (?:\*\*)?closed\b", re.I),
    "PO_NOT_FOUND": re.compile(r"\b(?:po|purchase order)\b[^.]{0,40}\b(?:was not|wasn't|is not|isn't|could not be|cannot be|can't be)\s+(?:found|located)\b|"
                               r"\bpo-\d{5}\b[^.]{0,30}\bnot (?:be )?found\b", re.I),
}


def mentions(text: str, value: str) -> bool:
    text = text.replace("**", "").replace("__", "")  # markdown emphasis must not hide a phrase
    t = text.lower()
    if value in CAUSE_PATTERNS and CAUSE_PATTERNS[value].search(text):
        return True
    if value in ENUM_PHRASES:
        return any(p in t for p in ENUM_PHRASES[value])
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value in dates(text)
    if IDS.fullmatch(value):
        return value in IDS.findall(text)
    if (n := norm_num(value)) is not None and re.fullmatch(r"[\d.,]+", value):
        found = numbers(text)
        if n in found:
            return True
        # A 2-dp ratio/percentage stated to 1 dp is the same fact (tune_t1: 5.87% written as 5.9%) - except near the
        # 2.00% tolerance, where rounding changes the meaning (2.06 -> "2.1", 2.01 -> "2.0").
        if re.fullmatch(r"\d+\.\d\d", value) and float(value) < 100 and abs(float(value) - 2.0) > 0.15:
            one = format(Decimal(value).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP).normalize(), "f")
            return one in found and not re.search(r"\b" + re.escape(value) + r"\b", text)
        return False
    if value.upper() in ("USD", "EUR"):
        return value.lower() in t
    words = [w for w in re.findall(r"[a-z]+", value.lower()) if len(w) > 3]
    return bool(words) and sum(w in t for w in words) / len(words) >= 0.6
