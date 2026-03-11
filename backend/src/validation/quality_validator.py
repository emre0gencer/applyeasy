"""
QualityValidator — entity matching, ATS checks, length checks, phrase blocklist.
Fully deterministic — no LLM calls.
"""

from __future__ import annotations

import re

from backend.src.models.schemas import (
    CandidateProfile,
    JobDescription,
    TailoredCoverLetter,
    TailoredResume,
    ValidationResult,
)

_GENERIC_PHRASES = [
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
]

# Approximate characters per page (single-column resume at 11pt)
_CHARS_PER_PAGE = 3200


def _extract_named_entities(text: str) -> set[str]:
    """
    Simple heuristic: extract capitalized multi-word phrases and numbers
    as pseudo-entities to check for hallucination.
    """
    # Numbers and percentages
    numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?%?\b", text))
    # Capitalized sequences (company/role names)
    caps = set(re.findall(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)+\b", text))
    return numbers | caps


def _check_truthfulness(
    resume: TailoredResume,
    cover_letter: TailoredCoverLetter,
    profile: CandidateProfile,
) -> list[str]:
    """
    Check that named entities (numbers, proper nouns) in outputs exist in source material.
    """
    warnings: list[str] = []
    source_text = profile.raw_text

    # Check resume bullets
    for exp in resume.experiences:
        for tb in exp.bullets:
            if tb.change.change_reason == "keyword_integration":
                entities_in_revised = _extract_named_entities(tb.text)
                entities_in_source = _extract_named_entities(tb.source_text)
                new_entities = entities_in_revised - entities_in_source
                if new_entities:
                    warnings.append(
                        f"Possible fabricated entity in rephrased bullet: {new_entities} "
                        f"(not in source: '{tb.source_text[:80]}')"
                    )

    # Check cover letter entities against full profile source
    cl_entities = _extract_named_entities(cover_letter.generated_text)
    source_entities = _extract_named_entities(source_text)
    suspicious = cl_entities - source_entities
    # Filter out small numbers (years, etc.) that may not be in extracted source
    suspicious = {e for e in suspicious if not re.match(r"^\d{1,4}$", e)}
    if suspicious:
        warnings.append(
            f"Cover letter contains entities not found in source profile: {suspicious}"
        )

    return warnings


def _check_keyword_coverage(
    resume: TailoredResume,
    jd: JobDescription,
) -> tuple[float, list[str], list[str]]:
    """Return (coverage_fraction, present_list, missing_list) for importance>=2 keywords."""
    high_kw = [k.term for k in jd.keywords if k.importance >= 2]
    if not high_kw:
        return 1.0, [], []

    # Build full resume text
    parts = [resume.summary or ""]
    for exp in resume.experiences:
        parts.append(exp.role_title)
        parts.extend(tb.text for tb in exp.bullets)
    for s in resume.skills:
        parts.append(s.name)
    full_text = " ".join(parts).lower()

    present = [k for k in high_kw if k.lower() in full_text]
    missing = [k for k in high_kw if k.lower() not in full_text]
    coverage = round(len(present) / len(high_kw), 2)
    return coverage, present, missing


def _estimate_page_count(resume: TailoredResume) -> float:
    """Rough estimate of resume page count based on character count."""
    parts = [resume.name, resume.summary or ""]
    for exp in resume.experiences:
        parts += [exp.role_title, exp.company, exp.start_date]
        parts += [tb.text for tb in exp.bullets]
    for edu in resume.education:
        parts += [edu.institution, edu.degree or ""]
    for proj in resume.projects:
        parts += [proj.name, proj.description or ""]
    for skill in resume.skills:
        parts.append(skill.name)
    total_chars = sum(len(p) for p in parts)
    return round(total_chars / _CHARS_PER_PAGE, 2)


def compute_raw_suitability(profile: CandidateProfile, jd: JobDescription) -> int:
    """
    Pessimistic suitability score from raw profile text vs JD — computed before tailoring.
    Intentionally harsh: rewards only what's genuinely present in the input.
    Returns 0-100; scores <50 should trigger the weak-profile alert.
    """
    high_kw = [k.term for k in jd.keywords if k.importance >= 2]

    if not high_kw:
        kw_score = 0.35  # no extractable JD keywords → pessimistic neutral
    else:
        profile_lower = profile.raw_text.lower()
        present = sum(1 for k in high_kw if k.lower() in profile_lower)
        kw_score = present / len(high_kw)

    exp_depth = min(len(profile.experiences) / 3, 1.0)
    clarity = profile.extraction_confidence

    # Pessimistic weighting — keyword match dominates; raw text rarely covers JD fully
    raw = kw_score * 55 + exp_depth * 25 + clarity * 20
    return max(0, min(100, round(raw)))


def validate(
    resume: TailoredResume,
    cover_letter: TailoredCoverLetter,
    profile: CandidateProfile,
    jd: JobDescription,
) -> ValidationResult:
    """Run all validation checks and return a ValidationResult."""
    flags: list[str] = []
    all_warnings: list[str] = []

    # 1. Keyword coverage
    coverage, present_kw, missing_kw = _check_keyword_coverage(resume, jd)
    if coverage < 0.6:
        flags.append(f"Low keyword coverage: {int(coverage * 100)}% of required terms present")

    # 2. Resume length
    page_est = _estimate_page_count(resume)
    if page_est > 1.2:
        flags.append(f"Resume may exceed 1 page (estimated {page_est:.1f} pages)")

    # 3. Cover letter length
    cl_words = cover_letter.word_count
    if cl_words > 400:
        flags.append(f"Cover letter is {cl_words} words (target: ≤350)")

    # 4. Generic phrase detection in cover letter
    cl_text_lower = cover_letter.generated_text.lower()
    found_generic = [p for p in _GENERIC_PHRASES if p in cl_text_lower]
    if found_generic:
        flags.append(f"Generic phrases detected in cover letter: {', '.join(found_generic)}")

    # 5. Propagate cover letter validation flags
    flags.extend(cover_letter.validation_flags)

    # 6. Truthfulness check
    truthfulness_warnings = _check_truthfulness(resume, cover_letter, profile)
    all_warnings.extend(truthfulness_warnings)
    if truthfulness_warnings:
        flags.append(f"{len(truthfulness_warnings)} potential truthfulness warning(s) — review change summary")

    # 7. Bullet changes summary
    rephrased = [c for c in resume.changes if c.change_reason == "keyword_integration"]
    if rephrased:
        flags.append(f"{len(rephrased)} bullet(s) rephrased — review change summary")

    all_flags = list(dict.fromkeys(flags))  # deduplicate, preserve order
    passed = not any(
        "truthfulness" in f.lower() or "fabricat" in f.lower()
        for f in all_flags
    )

    return ValidationResult(
        passed=passed,
        flags=all_flags,
        keyword_coverage=coverage,
        keywords_present=present_kw,
        keywords_missing=missing_kw,
        resume_page_estimate=page_est,
        cover_letter_word_count=cl_words,
        generic_phrases_found=found_generic,
        hallucination_warnings=all_warnings,
    )
