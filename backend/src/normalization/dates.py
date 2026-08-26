"""Date parsing and canonical rendering.

Resume source text carries dates in whatever form the candidate wrote them.
Extraction rule 5 preserves them verbatim, so a single rendered resume can show
"Jun 2022", "June 2022", "06/2022" and "2021-2023" side by side (all four were
observed in the shipped gallery samples).

This module gives every date one presentation without inventing precision:

  "June 2022" / "06/2022" / "2022-06"  -> "Jun 2022"
  "Summer 2022"                        -> "Summer 2022"   (season kept - see below)
  "2022"                               -> "2022"
  "present" / "current" / "now"        -> "Present"

Seasons are deliberately NOT converted to a month. "Summer 2022" -> "Jun 2022"
would state a start month the candidate never claimed, which the truthfulness
constraints of this app do not permit. Seasons are normalized in spelling and
capitalization only, and carry a representative month for sorting purposes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MONTHS: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Season -> (canonical label, representative month used only for sorting)
_SEASONS: dict[str, tuple[str, int]] = {
    "spring": ("Spring", 3),
    "summer": ("Summer", 6),
    "fall": ("Fall", 9),
    "autumn": ("Fall", 9),
    "winter": ("Winter", 12),
}

_PRESENT_TOKENS = {"present", "current", "currently", "now", "ongoing", "to date"}

# Any dash-like character candidates use to express a range.
_RANGE_SEP = r"[\-‐‑‒–—―]|\bto\b|\bthrough\b|\buntil\b"

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# Sort sentinels: Present outranks every real date; unknown sinks to the bottom.
_PRESENT_KEY = (9999, 12)
_UNKNOWN_KEY = (-1, -1)


@dataclass(frozen=True)
class ParsedDate:
    """A date recovered from free text, with enough structure to sort and render."""

    year: int | None = None
    month: int | None = None
    season: str | None = None      # canonical label ("Summer"), when the source used one
    is_present: bool = False
    raw: str = ""

    @property
    def is_known(self) -> bool:
        return self.is_present or self.year is not None

    @property
    def sort_key(self) -> tuple[int, int]:
        """(year, month) ordering key. Present sorts newest, unknown sorts oldest."""
        if self.is_present:
            return _PRESENT_KEY
        if self.year is None:
            return _UNKNOWN_KEY
        return (self.year, self.month or 0)

    def render(self) -> str:
        """Canonical presentation. Falls back to the raw string when unparseable."""
        if self.is_present:
            return "Present"
        if self.year is None:
            return self.raw.strip()
        if self.season:
            return f"{self.season} {self.year}"
        if self.month:
            return f"{_MONTH_ABBR[self.month]} {self.year}"
        return str(self.year)


def _is_present(token: str) -> bool:
    return token.strip().lower().strip(".") in _PRESENT_TOKENS


def parse_date(raw: str | None) -> ParsedDate:
    """Parse one date expression. Never raises - unparseable input round-trips."""
    if not raw:
        return ParsedDate(raw="")

    text = raw.strip()
    if _is_present(text):
        return ParsedDate(is_present=True, raw=text)

    lowered = text.lower()

    # Season + year: "Summer 2022", "fall 2021"
    for token, (label, month) in _SEASONS.items():
        if token in lowered:
            year_match = _YEAR_RE.search(text)
            if year_match:
                return ParsedDate(
                    year=int(year_match.group()), month=month, season=label, raw=text
                )

    # Numeric month/year: "06/2022", "6-2022"
    numeric = re.search(r"\b(\d{1,2})[/\-.](\d{4})\b", text)
    if numeric:
        month, year = int(numeric.group(1)), int(numeric.group(2))
        if 1 <= month <= 12:
            return ParsedDate(year=year, month=month, raw=text)

    # ISO-ish: "2022-06", "2022/6"
    numeric_iso = re.search(r"\b(\d{4})[/\-.](\d{1,2})\b", text)
    if numeric_iso:
        year, month = int(numeric_iso.group(1)), int(numeric_iso.group(2))
        if 1 <= month <= 12:
            return ParsedDate(year=year, month=month, raw=text)

    year_match = _YEAR_RE.search(text)

    # Month name + year: "Jun 2022", "June 2022", "Jun. 2022"
    month_match = re.search(r"\b([A-Za-z]{3,9})\.?\b", text)
    if month_match and year_match:
        month = _MONTHS.get(month_match.group(1).lower())
        if month:
            return ParsedDate(year=int(year_match.group()), month=month, raw=text)

    # Year alone
    if year_match:
        return ParsedDate(year=int(year_match.group()), raw=text)

    return ParsedDate(raw=text)


def split_range(raw: str | None) -> tuple[str, str] | None:
    """Split a single field that actually holds a range.

    resume_04 shipped an experience whose date field contained the whole range
    "2021-2023". Returns (start, end) when the field parses as a range of two
    known dates, else None.
    """
    if not raw:
        return None
    text = raw.strip()
    parts = [p.strip() for p in re.split(_RANGE_SEP, text, flags=re.IGNORECASE) if p.strip()]
    if len(parts) != 2:
        return None
    left, right = parse_date(parts[0]), parse_date(parts[1])
    if left.is_known and right.is_known:
        return parts[0], parts[1]
    return None


def canonicalize_range(start: str | None, end: str | None) -> tuple[str, str | None]:
    """Normalize an entry's (start_date, end_date) pair for presentation.

    Recovers the end date when the start field holds the whole range, so
    "2021-2023" in one field renders as two properly separated endpoints.
    """
    if not end:
        recovered = split_range(start)
        if recovered:
            start, end = recovered

    start_rendered = parse_date(start).render()
    end_rendered = parse_date(end).render() if end else None
    return start_rendered, (end_rendered or None)


def range_sort_key(start: str | None, end: str | None) -> tuple[tuple[int, int], tuple[int, int]]:
    """Ordering key for a dated entry: most recent end first, then most recent start.

    When no end date is given the entry sorts by its start date rather than being
    treated as ongoing, so a role listed with a single date is never silently
    promoted above a genuinely current one.
    """
    if not end:
        recovered = split_range(start)
        if recovered:
            start, end = recovered

    start_parsed = parse_date(start)
    end_parsed = parse_date(end) if end else start_parsed
    return end_parsed.sort_key, start_parsed.sort_key
