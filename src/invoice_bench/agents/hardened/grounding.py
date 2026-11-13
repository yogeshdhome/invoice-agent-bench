"""Deterministic post-generation grounding: every ID, number, percentage and date in the answer must appear in
the evidence (or be a small integer / policy constant). Owned by the HARDENED agent (the scorer has its own)."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

ID_RE = re.compile(r"\b(?:INV|PO|V|H|GR|PAY|EXC|POL|SV|VI)-[0-9A-Z]+\b")
NUM_RE = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
POLICY_CONSTANTS = {"2", "2.00", "50", "50.00", "10", "100"}


def _norm_num(s: str) -> str | None:
    try:
        return format(Decimal(s.replace(",", "")).normalize(), "f")
    except InvalidOperation:
        return None


def corpus(obj, out: set[str] | None = None) -> set[str]:
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            corpus(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            corpus(v, out)
    elif obj is not None:
        s = str(obj)
        out.add(s)
        for tok in ID_RE.findall(s) + DATE_RE.findall(s):
            out.add(tok)
        for n in NUM_RE.findall(s):
            if (nn := _norm_num(n)) is not None:
                out.add(nn)
    return out


def unsupported(answer: str, evidence_corpus: set[str]) -> list[str]:
    bad = []
    for tok in ID_RE.findall(answer):
        if tok not in evidence_corpus:
            bad.append(tok)
    for d in DATE_RE.findall(answer):
        if d not in evidence_corpus:
            bad.append(d)
    stripped = DATE_RE.sub(" ", ID_RE.sub(" ", answer))
    for n in NUM_RE.findall(stripped):
        nn = _norm_num(n)
        if nn is None or nn in evidence_corpus or nn in POLICY_CONSTANTS:
            continue
        if "." not in nn and int(nn) <= 31:
            continue
        bad.append(n)
    return sorted(set(bad))
