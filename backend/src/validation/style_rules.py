"""Shared style rules: phrase blocklists and prose-quality detectors.

Two prompt rules were previously stated to the model and never checked, so
violations shipped:

  "Vary action verbs - do not reuse the same verb across bullets in the same
   entry"  ->  resume_03 opened four bullets with "Built" and three with
   "Prepared"; resume_01 used "Designed" and "Built" three times each.

  "Never invent percentages, counts, ..."  ->  obeyed, but the model substitutes
   vague quantifiers instead of omitting the claim: "a large volume of monthly
   transactions", "significantly reduce the release cycle". A recruiter reads
   those as weaker than saying nothing.

This module turns both into detectors. It is also the single source of truth for
the generic-phrase blocklist, which previously existed twice with different
contents - the cover-letter generator prohibited 13 phrases while the validator
flagged 16, so the validator penalised phrases the generator was never told to
avoid.

Detectors are pure functions over text so the repair loop can reuse them to tell
the model exactly what to fix.
"""

from __future__ import annotations

import re
from collections import Counter

# Single source of truth. Imported by quality_validator (to flag) and by
# cover_letter_generator (to prohibit) so the two can never drift apart again.
GENERIC_PHRASES: tuple[str, ...] = (
    "excited to apply",
    "passionate about",
    "perfect fit",
    "team player",
    "fast learner",
    "proven track record",
    "seeking an opportunity",
    "highly motivated",
    "self-starter",
    "go-getter",
    "synergy",
    "leverage my skills",
    "hit the ground running",
    "results-driven",
    "detail-oriented",
    "hardworking",
)

# Vague quantifiers that stand in for a number the source never provided.
# Deliberately excludes "multiple", "several" and "many", which are too often
# legitimate ("multiple financial institution clients") to flag without noise.
HEDGE_PHRASES: tuple[str, ...] = (
    "a large volume of",
    "a large number of",
    "a high volume of",
    "a significant number of",
    "a wide range of",
    "a variety of",
    "large amounts of",
    "high volume of",
    "significantly",
    "substantially",
    "considerably",
    "dramatically",
    "markedly",
    "vastly",
    "greatly",
    "numerous",
)

# Leading tokens that are not the action verb, so the verb check looks past them.
_LEADING_SKIP = {"successfully", "effectively", "actively", "independently"}


def leading_verb(text: str) -> str | None:
    """Return the bullet's opening action verb in lowercase, or None.

    Bullets are expected to open with a past-tense action verb; anything that
    does not look like a word is ignored rather than guessed at.
    """
    stripped = re.sub(r"^[\s•\-\*·–○]+", "", text).strip()
    for token in stripped.split():
        word = re.sub(r"[^A-Za-z\-]", "", token).lower()
        if not word:
            continue
        if word in _LEADING_SKIP:
            continue
        return word
    return None


def find_repeated_verbs(bullets: list[str], threshold: int = 2) -> dict[str, int]:
    """Verbs opening `threshold` or more of the given bullets.

    Call with one entry's bullets and threshold=2 to enforce the per-entry rule,
    or with the whole resume and a higher threshold for a document-wide signal.
    """
    counts = Counter(
        verb for verb in (leading_verb(b) for b in bullets) if verb is not None
    )
    return {verb: n for verb, n in counts.items() if n >= threshold}


def find_hedges(text: str) -> list[str]:
    """Hedge phrases present in the text, in blocklist order."""
    lowered = text.lower()
    return [phrase for phrase in HEDGE_PHRASES if phrase in lowered]


def find_generic_phrases(text: str) -> list[str]:
    """Generic/filler phrases present in the text, in blocklist order."""
    lowered = text.lower()
    return [phrase for phrase in GENERIC_PHRASES if phrase in lowered]


def opens_with_name(summary: str, candidate_name: str) -> bool:
    """True when a resume summary opens by naming the candidate.

    All four shipped gallery samples did ("Alex Rivera has experience as a
    Software Engineer... He brings..."). A resume summary is written in
    implied first person; naming yourself in the third person is a convention
    violation no recruiter-facing resume should make.
    """
    if not summary or not candidate_name:
        return False
    first_name = candidate_name.strip().split()[0].lower()
    opening = summary.strip().lower()
    return bool(first_name) and opening.startswith(first_name)


def has_third_person_pronoun(summary: str) -> bool:
    """True when the summary refers to the candidate as he/she/they."""
    return bool(re.search(r"\b(he|she|they)\b", summary, re.IGNORECASE))
