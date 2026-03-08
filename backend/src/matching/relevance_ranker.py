"""
RelevanceRanker — cosine similarity scoring of experiences vs. JD requirements.
Uses local sentence-transformers (all-MiniLM-L6-v2). No API calls.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from backend.src.models.schemas import (
    Bullet,
    CandidateProfile,
    ExperienceEntry,
    ExperienceRelevanceMap,
    JobDescription,
    ProjectEntry,
    ScoredBullet,
    ScoredEntry,
)

_RELEVANCE_THRESHOLD = 0.25   # minimum score to include a bullet


@lru_cache(maxsize=1)
def _get_model():
    """Load embedding model once and cache it."""
    from sentence_transformers import SentenceTransformer  # type: ignore
    return SentenceTransformer("all-MiniLM-L6-v2")


def _embed(texts: list[str]) -> np.ndarray:
    model = _get_model()
    return model.encode(texts, normalize_embeddings=True, show_progress_bar=False)


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two unit-normalized vectors."""
    return float(np.dot(a, b))


def _build_job_query(jd: JobDescription) -> str:
    """Build a composite query string representing the job requirements."""
    parts = [jd.role_title]
    # Prioritize high-importance keywords
    high = [k.term for k in jd.keywords if k.importance >= 2]
    all_kw = [k.term for k in jd.keywords]
    req_texts = [r.text for r in jd.requirements if r.is_required][:10]
    parts.extend(high or all_kw[:10])
    parts.extend(req_texts[:5])
    return " | ".join(parts)


def _score_bullets(bullets: list[Bullet], job_query_vec: np.ndarray, jd: JobDescription) -> list[ScoredBullet]:
    if not bullets:
        return []
    texts = [b.text for b in bullets]
    vecs = _embed(texts)
    scored = []
    kw_terms = [k.term.lower() for k in jd.keywords]
    for bullet, vec in zip(bullets, vecs):
        sim = _cosine_sim(vec, job_query_vec)
        # Find keywords that appear literally in the bullet text
        matching_kw = [k for k in kw_terms if k in bullet.text.lower()]
        scored.append(ScoredBullet(
            bullet=bullet,
            relevance_score=round(sim, 4),
            matching_keywords=matching_kw,
        ))
    return scored


def _score_experience(
    exp: ExperienceEntry,
    entry_index: int,
    job_query_vec: np.ndarray,
    jd: JobDescription,
) -> ScoredEntry:
    scored_bullets = _score_bullets(exp.bullets, job_query_vec, jd)
    # Overall score = max bullet score (with role title boost)
    bullet_scores = [sb.relevance_score for sb in scored_bullets] or [0.0]
    overall = max(bullet_scores)
    # Boost if role title overlaps with JD title
    role_lower = exp.role_title.lower()
    jd_title_lower = jd.role_title.lower()
    title_words = set(jd_title_lower.split())
    role_words = set(role_lower.split())
    overlap = title_words & role_words
    if overlap:
        overall = min(1.0, overall + 0.05 * len(overlap))
    return ScoredEntry(
        entry_type="experience",
        entry_index=entry_index,
        overall_score=round(overall, 4),
        scored_bullets=scored_bullets,
    )


def _score_project(
    proj: ProjectEntry,
    entry_index: int,
    job_query_vec: np.ndarray,
    jd: JobDescription,
) -> ScoredEntry:
    bullets = proj.bullets or []
    # Also embed the description as a pseudo-bullet if no bullets
    if not bullets:
        from backend.src.models.schemas import Bullet as B
        bullets = [B(text=proj.description, source_text=proj.source_text)]
    scored_bullets = _score_bullets(bullets, job_query_vec, jd)
    bullet_scores = [sb.relevance_score for sb in scored_bullets] or [0.0]
    overall = max(bullet_scores)
    # Boost for tech overlap
    proj_tech = set(t.lower() for t in proj.technologies)
    jd_kw = set(k.term.lower() for k in jd.keywords)
    overlap = proj_tech & jd_kw
    if overlap:
        overall = min(1.0, overall + 0.04 * len(overlap))
    return ScoredEntry(
        entry_type="project",
        entry_index=entry_index,
        overall_score=round(overall, 4),
        scored_bullets=scored_bullets,
    )


def rank_relevance(profile: CandidateProfile, jd: JobDescription) -> ExperienceRelevanceMap:
    """Score all candidate experiences and projects against the job description."""
    job_query = _build_job_query(jd)
    job_query_vec = _embed([job_query])[0]

    scored_entries: list[ScoredEntry] = []

    for i, exp in enumerate(profile.experiences):
        scored_entries.append(_score_experience(exp, i, job_query_vec, jd))

    for i, proj in enumerate(profile.projects):
        scored_entries.append(_score_project(proj, i, job_query_vec, jd))

    # Sort by overall score descending
    scored_entries.sort(key=lambda e: e.overall_score, reverse=True)

    return ExperienceRelevanceMap(
        scored_entries=scored_entries,
        job_id=jd.job_id,
        profile_id=profile.profile_id,
    )
