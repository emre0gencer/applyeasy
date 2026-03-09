"""
ResumeTailoringEngine — selection + reorder + constrained LLM rephrasing.

Selection logic is deterministic. Rephrasing uses a single batched Groq call.
Summary generation uses llama-3.3-70b-versatile for quality.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from groq import Groq

from backend.src.models.schemas import (
    Bullet,
    BulletChange,
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    ExperienceRelevanceMap,
    JobDescription,
    KeywordEntry,
    ProjectEntry,
    ScoredBullet,
    ScoredEntry,
    Skill,
    TailoredBullet,
    TailoredExperience,
    TailoredResume,
)

_client: "Groq | None" = None

_FAST_MODEL = "llama-3.1-8b-instant"
_QUALITY_MODEL = "llama-3.3-70b-versatile"


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


# Limits
_MAX_EXPERIENCES = 3       # cap included experience entries
_MAX_BULLETS_PER_EXP = 3  # bullets per experience
_MAX_KEYWORD_INTEGRATIONS = 5  # per resume total
_ENTRY_THRESHOLD = 0.15   # minimum relevance score to include an entry


def _get_high_importance_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords if k.importance >= 2]


def _get_all_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords]


def _rephrase_bullets_batch(
    bullets: list[tuple[str, list[str]]],
    role_title: str,
) -> list[tuple[str, list[str]]]:
    """
    Single Groq call to rephrase ALL bullets following best job market practices.
    bullets = list of (original_text, keywords_to_try)
    Returns list of (revised_text, keywords_added).
    """
    if not bullets:
        return []

    system = (
        "You are a senior technical resume writer. Rewrite each bullet to be comprehensive, "
        "technically deep, and tightly tailored to the target role and its specific keywords.\n\n"

        "HARD RULES:\n"
        "1. Do NOT invent tools, technologies, metrics, dates, scope, or outcomes absent from the original.\n"
        "2. MANDATORY keyword integration: weave 2-3 of the provided target keywords into every bullet "
        "where technically accurate. If a bullet cannot fit 2, use at least 1.\n"
        "3. Length: 30-55 words per bullet (roughly 2 full lines). Write complete, substantive sentences — "
        "not fragments. Every bullet must demonstrate technical depth.\n"
        "4. Open with a strong past-tense action verb (e.g. Engineered, Implemented, Designed, Optimized, "
        "Developed, Automated, Analyzed, Built, Deployed, Integrated).\n"
        "5. Formula per bullet: verb + specific technical method/tool/stack + scope or scale + outcome or impact.\n"
        "6. Name technologies, libraries, frameworks, and patterns explicitly — never say 'a tool' or 'a library'.\n"
        "7. Replace vague verbs ('used', 'worked on', 'helped with') with precise technical actions.\n"
        "8. Vary action verbs — do not reuse the same verb across bullets in the same entry.\n"
        "9. No first-person pronouns, no filler adjectives ('passionate', 'innovative', 'dynamic').\n"
        "10. Each bullet must read as independently meaningful to a hiring manager scanning for the target role.\n\n"

        "Return ONLY valid JSON: "
        '{"results": [{"revised_text": str, "keywords_added": [str], "unchanged": bool}]}'
        " — one result per input bullet in the same order."
    )
    items = [
    {
        "index": i,
        "original": text,
        "keywords_to_try": kws,
        "target_role": role_title,
    }
    for i, (text, kws) in enumerate(bullets)
]
    user_msg = f"Target role: {role_title}\nBullets to rephrase:\n{json.dumps(items)}"

    resp = _get_client().chat.completions.create(
        model=_QUALITY_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        results = data.get("results", [])
        return [
            (r.get("revised_text", bullets[i][0]), r.get("keywords_added", []))
            for i, r in enumerate(results)
            if i < len(bullets)
        ]
    except (json.JSONDecodeError, AttributeError, IndexError):
        return [(text, []) for text, _ in bullets]


def _generate_summary(
    profile: CandidateProfile,
    jd: JobDescription,
    selected_experiences: list[TailoredExperience],
) -> str:
    """Generate a resume summary using llama-3.3-70b-versatile."""
    exp_titles = ", ".join(e.role_title for e in selected_experiences[:3])
    skills_snippet = ", ".join(s.name for s in profile.skills[:10])
    top_kw = ", ".join(_get_high_importance_keywords(jd)[:6])

    system = (
        "Write a 2-sentence resume summary for the given candidate targeting the given role.\n"
        "STRUCTURE:\n"
        "  Sentence 1: The candidate's years of experience, key technical background, and most relevant skills for this specific role. Incorporate 2-3 target keywords naturally.\n"
        "  Sentence 2: Express genuine aspiration and enthusiasm for the specific field/industry of the target role, and briefly state the unique value the candidate brings.\n"
        "RULES:\n"
        "1. Only reference background elements present in the provided profile data.\n"
        "2. Do NOT fabricate achievements, metrics, or skills not listed.\n"
        "3. No generic phrases: 'passionate', 'results-driven', 'team player', 'fast learner', 'proven track record'.\n"
        "4. Maximum 70 words total. Output only the 2 sentences — no labels, no extra text."
    )
    user_msg = (
        f"Candidate name: {profile.name}\n"
        f"Recent roles: {exp_titles}\n"
        f"Skills: {skills_snippet}\n"
        f"Target role: {jd.role_title} at {jd.company_name or 'the company'}\n"
        f"Target keywords: {top_kw}\n"
        f"Seniority: {jd.seniority_level}"
    )

    resp = _get_client().chat.completions.create(
        model=_QUALITY_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


def _select_and_tailor_experiences(
    profile: CandidateProfile,
    relevance_map: ExperienceRelevanceMap,
    jd: JobDescription,
    keyword_integration_budget: list[int],  # mutable counter [remaining]
) -> list[TailoredExperience]:
    """Select top experiences and tailor their bullets using a single batch LLM call."""
    exp_entries = [e for e in relevance_map.scored_entries if e.entry_type == "experience"]
    exp_entries = [e for e in exp_entries if e.overall_score >= _ENTRY_THRESHOLD]

    # Always include research/researcher entries if present — keep top scored others
    def _is_research(idx: int) -> bool:
        if idx >= len(profile.experiences):
            return False
        return any(kw in profile.experiences[idx].role_title.lower()
                   for kw in ("research", "researcher"))

    research = [e for e in exp_entries if _is_research(e.entry_index)]
    non_research = [e for e in exp_entries if not _is_research(e.entry_index)]
    # Fill up to _MAX_EXPERIENCES: research first, then top-scored non-research
    slots_left = _MAX_EXPERIENCES - len(research)
    exp_entries = research + non_research[:max(slots_left, 0)]
    exp_entries = exp_entries[:_MAX_EXPERIENCES]

    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    role_title = jd.role_title

    # Collect all bullets that need rephrasing in one pass
    # Structure: list of (exp_idx, bullet_idx_in_sorted, original_text, kws)
    rephrase_queue: list[tuple[int, int, str, list[str]]] = []
    # Per-exp sorted bullet lists for later assembly
    per_exp_sorted: list[list[ScoredBullet]] = []

    for exp_i, scored_entry in enumerate(exp_entries):
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            per_exp_sorted.append([])
            continue
        sorted_bullets = sorted(
            scored_entry.scored_bullets,
            key=lambda sb: sb.relevance_score,
            reverse=True,
        )[:_MAX_BULLETS_PER_EXP]
        per_exp_sorted.append(sorted_bullets)

        # Send ALL bullets through rephrasing — pass full keyword pool, high-importance first
        target_kws = list(dict.fromkeys(high_kw + all_kw))[:10]
        for b_i, sb in enumerate(sorted_bullets):
            rephrase_queue.append((exp_i, b_i, sb.bullet.text, target_kws))

    # Single batch call for all bullets needing rephrasing
    batch_inputs = [(text, kws) for _, _, text, kws in rephrase_queue]
    batch_results = _rephrase_bullets_batch(batch_inputs, role_title) if batch_inputs else []

    # Map results back: (exp_i, b_i) → (revised_text, keywords_added)
    rephrase_map: dict[tuple[int, int], tuple[str, list[str]]] = {}
    for qi, (exp_i, b_i, _original_text, _) in enumerate(rephrase_queue):
        if qi < len(batch_results):
            revised, kws_added = batch_results[qi]
            rephrase_map[(exp_i, b_i)] = (revised, kws_added)

    # Assemble TailoredExperience objects
    tailored_experiences: list[TailoredExperience] = []
    for exp_i, scored_entry in enumerate(exp_entries):
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            continue
        exp = profile.experiences[idx]
        sorted_bullets = per_exp_sorted[exp_i]

        tailored_bullets: list[TailoredBullet] = []
        for b_i, sb in enumerate(sorted_bullets):
            original_text = sb.bullet.text
            if (exp_i, b_i) in rephrase_map:
                revised_text, keywords_added = rephrase_map[(exp_i, b_i)]
                change_reason = "keyword_integration" if keywords_added else "unchanged"
            else:
                revised_text = original_text
                keywords_added = []
                change_reason = "unchanged"

            tailored_bullets.append(TailoredBullet(
                text=revised_text,
                source_text=sb.bullet.source_text,
                change=BulletChange(
                    original_text=original_text,
                    revised_text=revised_text,
                    change_reason=change_reason,
                    keywords_added=keywords_added,
                ),
                relevance_score=sb.relevance_score,
            ))

        tailored_experiences.append(TailoredExperience(
            company=exp.company,
            role_title=exp.role_title,
            start_date=exp.start_date,
            end_date=exp.end_date,
            location=exp.location,
            bullets=tailored_bullets,
        ))

    return tailored_experiences


def _compute_keyword_coverage(resume_text: str, jd: JobDescription) -> float:
    """Fraction of importance>=2 JD keywords present in the resume text."""
    high_kw = [k.term.lower() for k in jd.keywords if k.importance >= 2]
    if not high_kw:
        return 1.0
    text_lower = resume_text.lower()
    present = [k for k in high_kw if k in text_lower]
    return round(len(present) / len(high_kw), 2)


def tailor_resume(
    profile: CandidateProfile,
    jd: JobDescription,
    relevance_map: ExperienceRelevanceMap,
) -> TailoredResume:
    """Build a tailored resume from the profile and relevance scores."""
    keyword_budget = [_MAX_KEYWORD_INTEGRATIONS]

    tailored_experiences = _select_and_tailor_experiences(
        profile, relevance_map, jd, keyword_budget
    )

    # Generate summary
    summary = _generate_summary(profile, jd, tailored_experiences)

    # Collect all bullet changes for the audit trail
    all_changes: list[BulletChange] = []
    for te in tailored_experiences:
        all_changes.extend(tb.change for tb in te.bullets)

    # Build full resume text for keyword coverage check
    full_text_parts = [summary]
    for te in tailored_experiences:
        full_text_parts.append(te.role_title)
        full_text_parts.extend(tb.text for tb in te.bullets)
    for s in profile.skills:
        full_text_parts.append(s.name)
    full_text = " ".join(full_text_parts)

    keyword_coverage = _compute_keyword_coverage(full_text, jd)

    return TailoredResume(
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin,
        github=profile.github,
        location=profile.location,
        summary=summary,
        experiences=tailored_experiences,
        education=profile.education,
        projects=profile.projects[:2],
        skills=profile.skills,
        awards=profile.awards,
        leadership_items=profile.leadership_items,
        keyword_coverage=keyword_coverage,
        changes=all_changes,
    )
