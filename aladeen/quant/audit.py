"""Number audit: every figure an agent writes must trace back to the fact pack.

Agents are told not to introduce numbers. This module checks. Each number in an agent's
text is compared with the numbers in the material that agent was given (within rounding
tolerance, and allowing for percent <-> decimal forms). Unmatched figures are listed in
the report's QA appendix and passed to the CIO so it
can discount the claims that rest on them.
"""

from __future__ import annotations

import re

_NUM = re.compile(
    r"(?<![A-Za-z0-9_])(?P<sign>[-+−])?(?:₹|Rs\.?\s?)?(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<unit>%|x\b|pp\b|bps\b|cr\b|crore|lakh|bn\b)?",
    re.IGNORECASE,
)


def extract_numbers(text: str) -> list[tuple[str, float, str]]:
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(0).strip()
        try:
            v = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        if m.group("sign") in ("-", "−"):
            v = -v
        out.append((raw, v, (m.group("unit") or "").lower()))
    return out


def _ignorable(v: float, unit: str) -> bool:
    if unit in ("%", "x", "pp", "bps", "cr", "crore", "lakh", "bn"):
        return False
    if float(v).is_integer() and (abs(v) <= 12 or 1990 <= v <= 2100):
        return True  # counts, months, years
    return False


def known_set(*texts: str, extra: list[float] | None = None) -> list[float]:
    vals = {round(v, 6) for t in texts for _, v, _ in extract_numbers(t)}
    for v in extra or []:
        if v is not None:
            vals.add(round(float(v), 6))
    return sorted(vals)


def _matches(v: float, known: list[float], tol: float) -> bool:
    cands = (v, v / 100, v * 100, -v)
    for k in known:
        for c in cands:
            if abs(c - k) <= max(abs(k) * tol, 0.051 if abs(k) >= 1 else 0.0006):
                return True
    return False


def audit_text(text: str, known: list[float], tol: float = 0.011) -> list[str]:
    """Return raw strings of numbers in ``text`` that do not match any known value."""
    bad = []
    for raw, v, unit in extract_numbers(text):
        if _ignorable(v, unit):
            continue
        if not _matches(v, known, tol):
            bad.append(raw)
    return list(dict.fromkeys(bad))
