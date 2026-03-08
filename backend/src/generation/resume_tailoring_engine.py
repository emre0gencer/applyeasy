"""
ResumeTailoringEngine — selection + reorder + constrained LLM rephrasing.

Selection logic is deterministic. Rephrasing uses Claude Haiku at temp=0.
Summary generation uses Claude Sonnet.
"""

from __future__ import annotations

from typing import Optional

import anthropic

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

_client = anthropic.Anthropic()

# Limits
_MAX_EXPERIENCES = 4       # cap included experience entries
_MAX_BULLETS_PER_EXP = 5  # bullets per experience
_MAX_KEYWORD_INTEGRATIONS = 5  # per resume total
_ENTRY_THRESHOLD = 0.15   # minimum relevance score to include an entry


def _get_high_importance_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords if k.importance >= 2]


def _get_all_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords]


def _rephrase_bullet(
    bullet_text: str,
    keywords_to_integrate: list[str],
    role_title: str,
) -> tuple[str, list[str]]:
    """
    Ask Claude Haiku to rephrase a bullet to include keywords where natural.
    Returns (revised_text, keywords_actually_added).
    """
    if not keywords_to_integrate:
        return bullet_text, []

    tool = {
        "name": "rephrase_bullet",
        "description": "Rephrase a resume bullet point to integrate keywords.",
        "input_schema": {
            "type": "object",
            "properties": {
                "revised_text": {
                    "type": "string",
                    "description": "The rephrased bullet. Return original if keywords don't fit naturally.",
                },
                "keywords_added": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of keywords actually integrated (empty if none fit naturally)",
                },
                "unchanged": {
                    "type": "boolean",
                    "description": "True if the bullet was returned unchanged",
                },
            },
            "required": ["revised_text", "keywords_added", "unchanged"],
        },
    }

    system = (
        "You are a conservative resume editor. Rephrase bullets to include keywords where accurate and natural.\n"
        "RULES:\n"
        "1. Do NOT change numbers, metrics, or factual claims.\n"
        "2. Do NOT add new claims or skills not in the original.\n"
        "3. Do NOT imply expertise with skills not demonstrated.\n"
        "4. Return the original text if keywords don't fit naturally.\n"
        "5. Keep the same sentence structure where possible.\n"
        "6. Bullets should remain concise (under 2 lines)."
    )
    user_msg = (
        f"Original bullet: {bullet_text}\n"
        f"Keywords to integrate (if natural): {', '.join(keywords_to_integrate)}\n"
        f"Target role: {role_title}"
    )

    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        temperature=0,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": "rephrase_bullet"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "rephrase_bullet":
            data = block.input
            return data.get("revised_text", bullet_text), data.get("keywords_added", [])

    return bullet_text, []


def _generate_summary(
    profile: CandidateProfile,
    jd: JobDescription,
    selected_experiences: list[TailoredExperience],
) -> str:
    """Generate a resume summary using Claude Sonnet."""
    exp_titles = ", ".join(e.role_title for e in selected_experiences[:3])
    skills_snippet = ", ".join(s.name for s in profile.skills[:10])
    top_kw = ", ".join(_get_high_importance_keywords(jd)[:6])

    system = (
        "Write a concise 2-3 sentence resume summary for the given candidate targeting the given role.\n"
        "RULES:\n"
        "1. Only reference background elements present in the provided profile data.\n"
        "2. Do NOT fabricate achievements, metrics, or skills not listed.\n"
        "3. Naturally incorporate 2-3 of the target keywords where accurate.\n"
        "4. No generic phrases: 'passionate', 'results-driven', 'team player', 'fast learner'.\n"
        "5. Maximum 60 words."
    )
    user_msg = (
        f"Candidate name: {profile.name}\n"
        f"Recent roles: {exp_titles}\n"
        f"Skills: {skills_snippet}\n"
        f"Target role: {jd.role_title} at {jd.company_name or 'the company'}\n"
        f"Target keywords: {top_kw}\n"
        f"Seniority: {jd.seniority_level}"
    )

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()


def _select_and_tailor_experiences(
    profile: CandidateProfile,
    relevance_map: ExperienceRelevanceMap,
    jd: JobDescription,
    keyword_integration_budget: list[int],  # mutable counter [remaining]
) -> list[TailoredExperience]:
    """Select top experiences and tailor their bullets."""
    exp_entries = [e for e in relevance_map.scored_entries if e.entry_type == "experience"]
    exp_entries = [e for e in exp_entries if e.overall_score >= _ENTRY_THRESHOLD]
    exp_entries = exp_entries[:_MAX_EXPERIENCES]

    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    role_title = jd.role_title
    tailored_experiences: list[TailoredExperience] = []
    all_changes: list[BulletChange] = []

    for scored_entry in exp_entries:
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            continue
        exp = profile.experiences[idx]

        # Sort bullets by relevance descending, take top N
        sorted_bullets = sorted(
            scored_entry.scored_bullets,
            key=lambda sb: sb.relevance_score,
            reverse=True,
        )[:_MAX_BULLETS_PER_EXP]

        tailored_bullets: list[TailoredBullet] = []
        for sb in sorted_bullets:
            original_text = sb.bullet.text
            revised_text = original_text
            keywords_added: list[str] = []
            change_reason = "unchanged"

            # Attempt keyword integration if budget remains and bullet is relevant
            if keyword_integration_budget[0] > 0 and sb.relevance_score >= 0.2:
                # Find keywords not already in the bullet
                existing = original_text.lower()
                missing_kw = [k for k in (high_kw or all_kw[:5]) if k.lower() not in existing][:2]
                if missing_kw:
                    revised_text, keywords_added = _rephrase_bullet(
                        original_text, missing_kw, role_title
                    )
                    if keywords_added:
                        change_reason = "keyword_integration"
                        keyword_integration_budget[0] -= len(keywords_added)

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
        location=profile.location,
        summary=summary,
        experiences=tailored_experiences,
        education=profile.education,
        projects=profile.projects,
        skills=profile.skills,
        awards=profile.awards,
        keyword_coverage=keyword_coverage,
        changes=all_changes,
    )
