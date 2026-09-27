"""Keyword dictionary for complaint text. A port of the desk's src/lib/agent/themes.ts.

Patterns are the desk's regexes unchanged; re.ASCII matches JavaScript's ASCII \\w and \\b.
"""

import re
from dataclasses import dataclass

_FLAGS = re.IGNORECASE | re.ASCII


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class ThemeMatch:
    id: str
    label: str
    phrase: str


def _theme(id: str, label: str, pattern: str) -> Theme:
    return Theme(id, label, re.compile(pattern, _FLAGS))


THEMES = [
    _theme("estimated_reading", "Estimated reading", r"\bestimat(?:e|ed|es|ion)\b"),
    _theme(
        "tariff_change",
        "Price or tariff change",
        r"\btariff\b|\bunit rate\b|\bprice (?:rise|increase|went up)\b"
        r"|\brates? (?:went up|changed?|increase)",
    ),
    _theme("direct_debit", "Direct Debit change", r"\bdirect debit\b"),
    _theme("refund", "Refund or credit", r"\brefund\w*\b|\bin credit\b|\boverpa(?:id|y|yment)\b"),
    _theme(
        "missed_appointment",
        "Missed appointment",
        r"\bmissed (?:the |my )?(?:appointment|visit)\b|\bno[- ]show\b"
        r"|\b(?:didn'?t|never) (?:turn up|came|come)\b",
    ),
    _theme(
        "chasing",
        "Chasing a previous contact",
        r"\bno (?:reply|response)\b|\bstill waiting\b|\bheard nothing\b"
        r"|\b(?:second|third|fourth) time\b|\bchas(?:e|ed|ing)\b",
    ),
    _theme(
        "no_supply",
        "No supply",
        r"\bpower cut\b|\bno (?:power|electricity|water)\b|\boutage\b"
        r"|\bsupply (?:is )?(?:off|cut|interrupted)\b",
    ),
    _theme("smart_meter", "Smart meter", r"\bsmart meter\b|\bin-home display\b"),
    _theme(
        "water_quality",
        "Water quality",
        r"\bdiscolou?red\b|\bbrown water\b|\b(?:smells?|tastes?) (?:of|like|odd|strange|funny)\b"
        r"|\bcloudy\b",
    ),
    _theme(
        "bill_explanation",
        "Wants the bill explained",
        r"\bexplain\w*\b|\bbreakdown\b|\bdon'?t understand\b"
        r"|\bwhat (?:is|are) (?:this|these|the) charges?\b",
    ),
    _theme(
        "moving_home",
        "Moving home",
        r"\bmov(?:ed|ing) (?:out|in|house|home)\b|\bprevious (?:tenant|occupier)\b",
    ),
    _theme("regulator", "Mentions regulator or ombudsman", r"\bombudsman\b|\bregulator\b"),
]

_INFORMATION_REQUEST = re.compile(
    r"\bhow (?:do|can) i\b|\bwhen (?:is|will|do)\b|\bwhat (?:is|are|does)\b|\bexplain\w*\b"
    r"|\bbreakdown\b|\bdon'?t understand\b",
    _FLAGS,
)


def match_themes(text: str) -> list[ThemeMatch]:
    """All dictionary themes found in the text, with the phrase that matched."""
    found = []
    for theme in THEMES:
        match = theme.pattern.search(text)
        if match:
            found.append(ThemeMatch(theme.id, theme.label, match.group(0)))
    return found


def is_information_request(text: str) -> bool:
    """A question the customer could answer themselves with the right information."""
    return _INFORMATION_REQUEST.search(text) is not None
