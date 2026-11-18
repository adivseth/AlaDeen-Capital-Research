"""Methodology knowledge base (Damodaran, Graham, Graham & Dodd; India-calibrated).

These markdown notes are injected into agent prompts so every run applies the same
framework. Edit them to change how the agents think.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

_DIR = Path(__file__).parent
FILES = {
    "dcf": "dcf-valuation.md",
    "multiples": "multiples-valuation.md",
    "statements": "financial-statement-analysis.md",
    "value": "value-investing-framework.md",
    "sector": "sector-valuation.md",
}


@cache
def load(name: str) -> str:
    return (_DIR / FILES[name]).read_text(encoding="utf-8")


def section(name: str, heading: str) -> str:
    """Return one '## ' section of a knowledge file whose heading contains ``heading``."""
    text = load(name)
    parts = re.split(r"(?m)^## ", text)
    for p in parts:
        if heading.lower() in p.split("\n", 1)[0].lower():
            return "## " + p.strip()
    return ""
