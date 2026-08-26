"""Presentation ordering and date canonicalization for resume entries.

The pipeline *selects* entries by relevance to the job description, which is
correct - the most relevant three roles are the ones worth the page space. It
then *presented* them in that same relevance order, which is not: reverse
chronological is a hard recruiter convention, and two of the four shipped
gallery samples violated it (resume_03 read Jan 2022 -> Jun 2022 -> Jun 2021).

This module draws the line between the two: selection stays relevance-driven,
presentation becomes date-driven. It also applies the canonical date rendering
from `dates.py`, so one document never mixes "Jun 2022" with "June 2022".

Every function returns new objects; nothing is mutated in place.
"""

from __future__ import annotations

from typing import TypeVar

from backend.src.normalization.dates import (
    canonicalize_range,
    parse_date,
    range_sort_key,
)

T = TypeVar("T")

# Entries whose dates we could not parse keep their original relative order and
# sort after everything dated, rather than jumping to the top of the section.
_UNDATED_LAST = (-1, -1)


def _stable_sort(items: list[T], key) -> list[T]:
    """Sort descending by `key`, breaking ties on original position.

    Python's sort is stable, so pairing each item with its index and sorting on
    the negated key is unnecessary - sorting descending on the key alone already
    preserves input order among equals.
    """
    return sorted(items, key=key, reverse=True)


def normalize_experiences(experiences: list) -> list:
    """Canonicalize dates and present experiences in reverse-chronological order.

    Accepts either `ExperienceEntry` or `TailoredExperience` - both carry
    `start_date` / `end_date`.
    """
    if not experiences:
        return experiences

    normalized = []
    for exp in experiences:
        start, end = canonicalize_range(exp.start_date, exp.end_date)
        normalized.append(exp.model_copy(update={"start_date": start, "end_date": end}))

    return _stable_sort(
        normalized, key=lambda e: range_sort_key(e.start_date, e.end_date)
    )


def normalize_education(education: list) -> list:
    """Canonicalize graduation dates and order most-recent-first."""
    if not education:
        return education

    normalized = [
        edu.model_copy(
            update={"graduation_date": parse_date(edu.graduation_date).render() or None}
        )
        if edu.graduation_date
        else edu
        for edu in education
    ]

    return _stable_sort(
        normalized, key=lambda e: parse_date(e.graduation_date).sort_key
    )


def normalize_projects(projects: list) -> list:
    """Canonicalize project dates and order most-recent-first.

    Undated projects keep their incoming order (which is relevance order) and
    follow the dated ones, so a project without a date is never promoted above
    recent work by an unknown-date sentinel.
    """
    if not projects:
        return projects

    normalized = [
        proj.model_copy(update={"date": parse_date(proj.date).render() or None})
        if proj.date
        else proj
        for proj in projects
    ]

    dated = [p for p in normalized if parse_date(p.date).is_known]
    undated = [p for p in normalized if not parse_date(p.date).is_known]

    ordered_dated = _stable_sort(dated, key=lambda p: parse_date(p.date).sort_key)
    return ordered_dated + undated
