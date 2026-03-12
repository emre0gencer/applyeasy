"""
QualityValidator — entity matching, ATS checks, length checks, phrase blocklist.
Fully deterministic — no LLM calls.

v2: Added compute_raw_suitability_v2 with multi-factor scoring (must-have
coverage, semantic relevance, evidence quality, preferred coverage, clarity).
Added evidence quality checks: generic phrases in resume bullets, bullet
redundancy, evidence thinness, and keyword-stuffing robustness detection.
"""

from __future__ import annotations

import re
from typing import Optional

from backend.src.models.schemas import (
    CandidateProfile,
    ExperienceRelevanceMap,
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


# ---------------------------------------------------------------------------
# v2: Raw suitability scoring (multi-factor)
# ---------------------------------------------------------------------------

def compute_raw_suitability(profile: CandidateProfile, jd: JobDescription) -> int:
    """
    Pessimistic suitability score from raw profile text vs JD — computed before tailoring.
    Intentionally harsh: rewards only what's genuinely present in the input.
    Returns 0-100; scores <50 should trigger the weak-profile alert.

    Preserved for backward compatibility. Delegates to v2 when possible.
    """
    score, _ = compute_raw_suitability_v2(profile, jd, relevance_map=None)
    return score


def compute_raw_suitability_v2(
    profile: CandidateProfile,
    jd: JobDescription,
    relevance_map: Optional[ExperienceRelevanceMap] = None,
) -> tuple[int, dict[str, float]]:
    """
    Multi-factor suitability score. Returns (score_0_100, breakdown_dict).

    Components:
      35%  must-have coverage   — how many required requirements appear in the raw profile
      10%  preferred coverage   — how many preferred requirements appear in the raw profile
      30%  semantic relevance   — avg top-3 bullet_contribution_scores from relevance map
      15%  evidence quality     — avg evidence_strength of top candidate bullets
      10%  extraction clarity   — confidence from document ingestion

    When relevance_map is None (early pipeline call), semantic relevance and
    evidence quality fall back to neutral estimates.
    """
    raw_lower = profile.raw_text.lower()

    # ── Must-have coverage (35%) ──────────────────────────────────────────
    must_have = jd.must_have_requirements or [r.text for r in jd.requirements if r.is_required]
    if must_have:
        # Word-overlap match: at least one significant word (>3 chars) from each
        # requirement must appear in the raw profile text
        def _req_matched(req_text: str) -> bool:
            words = [w.lower() for w in req_text.split() if len(w) > 3]
            return any(w in raw_lower for w in words) if words else False
        mh_hits = sum(1 for r in must_have if _req_matched(r))
        must_have_score = mh_hits / len(must_have)
    else:
        # Fallback: keyword presence if no structured requirements
        high_kw = [k.term for k in jd.keywords if k.importance >= 2]
        if high_kw:
            kw_hits = sum(1 for k in high_kw if k.lower() in raw_lower)
            must_have_score = kw_hits / len(high_kw)
        else:
            must_have_score = 0.35  # pessimistic neutral

    # ── Preferred coverage (10%) ──────────────────────────────────────────
    preferred = jd.preferred_requirements or [r.text for r in jd.requirements if not r.is_required]
    if preferred:
        def _req_matched_pref(req_text: str) -> bool:
            words = [w.lower() for w in req_text.split() if len(w) > 3]
            return any(w in raw_lower for w in words) if words else False
        pref_hits = sum(1 for r in preferred if _req_matched_pref(r))
        preferred_score = pref_hits / len(preferred)
    else:
        preferred_score = 0.4  # neutral if no preferred requirements

    # ── Semantic relevance (30%) ──────────────────────────────────────────
    if relevance_map and relevance_map.scored_entries:
        exp_entries = [e for e in relevance_map.scored_entries if e.entry_type == "experience"]
        top_contribution_scores = sorted(
            [e.overall_score for e in exp_entries], reverse=True
        )[:3]
        semantic_score = (
            sum(top_contribution_scores) / len(top_contribution_scores)
            if top_contribution_scores else 0.2
        )
    else:
        # Fallback when relevance map not yet available
        semantic_score = 0.30

    # ── Evidence quality (15%) ────────────────────────────────────────────
    if relevance_map and relevance_map.scored_entries:
        ev_scores: list[float] = []
        for entry in relevance_map.scored_entries[:4]:
            for sb in entry.scored_bullets[:3]:
                if sb.evidence is not None:
                    ev_scores.append(sb.evidence.evidence_strength)
        evidence_score = sum(ev_scores) / len(ev_scores) if ev_scores else 0.25
    else:
        evidence_score = 0.25  # neutral fallback

    # ── Extraction clarity (10%) ──────────────────────────────────────────
    clarity = profile.extraction_confidence

    # ── Composite score ───────────────────────────────────────────────────
    raw = (
        must_have_score  * 35
        + preferred_score * 10
        + semantic_score  * 30
        + evidence_score  * 15
        + clarity         * 10
    )
    score = max(0, min(100, round(raw)))

    breakdown: dict[str, float] = {
        "must_have_coverage":  round(must_have_score, 3),
        "preferred_coverage":  round(preferred_score, 3),
        "semantic_relevance":  round(semantic_score, 3),
        "evidence_quality":    round(evidence_score, 3),
        "extraction_clarity":  round(clarity, 3),
        "raw_total":           round(raw, 1),
    }
    return score, breakdown


# ---------------------------------------------------------------------------
# v2: Evidence quality checks
# ---------------------------------------------------------------------------

def _check_resume_generic_phrases(resume: TailoredResume) -> list[str]:
    """Detect generic/filler phrases in resume bullets (not just cover letter)."""
    found: set[str] = set()
    for exp in resume.experiences:
        for tb in exp.bullets:
            text_lower = tb.text.lower()
            for phrase in _GENERIC_PHRASES:
                if phrase in text_lower:
                    found.add(phrase)
    return sorted(found)


def _check_bullet_redundancy(resume: TailoredResume) -> list[str]:
    """
    Flag pairs of resume bullets with very high word-overlap (>70% shared words).
    Indicates the rewriter may have produced near-duplicate content.
    """
    flags: list[str] = []
    all_bullets: list[str] = []
    for exp in resume.experiences:
        for tb in exp.bullets:
            all_bullets.append(tb.text)

    for i in range(len(all_bullets)):
        for j in range(i + 1, len(all_bullets)):
            words_i = set(all_bullets[i].lower().split())
            words_j = set(all_bullets[j].lower().split())
            min_len = min(len(words_i), len(words_j))
            if min_len < 6:
                continue  # too short to meaningfully compare
            overlap = len(words_i & words_j) / min_len
            if overlap > 0.70:
                flags.append(
                    f"Possibly redundant bullets ({overlap:.0%} word overlap): "
                    f"'{all_bullets[i][:60]}...'"
                )
    return flags


def _check_evidence_quality(resume: TailoredResume) -> list[str]:
    """
    Flag long bullets (>50 words) with low evidence signals.
    These are likely verbose but informationally thin.
    """
    from backend.src.analysis.evidence_extractor import extract_evidence
    flags: list[str] = []
    for exp in resume.experiences:
        for tb in exp.bullets:
            word_count = len(tb.text.split())
            if word_count > 50:
                evidence = extract_evidence(tb.text)
                if evidence.evidence_strength < 0.20:
                    flags.append(
                        f"Long bullet ({word_count}w) with low evidence signals "
                        f"(strength={evidence.evidence_strength:.2f}): '{tb.text[:80]}...'"
                    )
    return flags


def _check_robustness(resume: TailoredResume) -> list[str]:
    """
    Detect bullets where keyword count increased significantly but evidence
    strength did not improve — a signal of keyword-heavy rewrites without
    corresponding information gain.
    """
    from backend.src.analysis.evidence_extractor import extract_evidence
    flags: list[str] = []
    for exp in resume.experiences:
        for tb in exp.bullets:
            if tb.change.change_reason != "keyword_integration":
                continue
            if not tb.change.original_text or not tb.change.keywords_added:
                continue
            kw_gain = len(tb.change.keywords_added)
            if kw_gain < 3:
                continue  # only flag aggressive keyword insertion
            orig_ev = extract_evidence(tb.change.original_text)
            revised_ev = extract_evidence(tb.text)
            ev_gain = revised_ev.evidence_strength - orig_ev.evidence_strength
            if ev_gain < 0.05:
                flags.append(
                    f"Keyword-heavy rewrite with minimal evidence gain "
                    f"(+{kw_gain} keywords, evidence delta {ev_gain:+.2f}): "
                    f"'{tb.text[:70]}...'"
                )
    return flags


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate(
    resume: TailoredResume,
    cover_letter: TailoredCoverLetter,
    profile: CandidateProfile,
    jd: JobDescription,
    score_breakdown: Optional[dict[str, float]] = None,
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

    # ── v2: Evidence quality checks ──────────────────────────────────────
    evidence_flags: list[str] = []

    # 8. Generic phrases in resume bullets (not just cover letter)
    resume_generic = _check_resume_generic_phrases(resume)
    if resume_generic:
        evidence_flags.append(
            f"Generic phrases in resume bullets: {', '.join(resume_generic)}"
        )

    # 9. Redundant bullets
    redundancy_flags = _check_bullet_redundancy(resume)
    evidence_flags.extend(redundancy_flags)

    # 10. Evidence thinness (long bullets with low information density)
    thinness_flags = _check_evidence_quality(resume)
    evidence_flags.extend(thinness_flags)

    # 11. Robustness check (keyword gain without evidence gain)
    robustness_flags = _check_robustness(resume)
    evidence_flags.extend(robustness_flags)
    # ─────────────────────────────────────────────────────────────────────

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
        # v2 fields
        score_breakdown=score_breakdown or {},
        evidence_quality_flags=evidence_flags,
    )
