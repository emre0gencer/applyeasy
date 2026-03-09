"""
CoverLetterGenerator — evidence-first LLM narrative generation.
Two-call chain: alignment identification (llama-3.1-8b-instant, JSON mode) →
generation (llama-3.3-70b-versatile, temp=0.4).
"""

from __future__ import annotations

import json
import os
import re

from groq import Groq

from backend.src.models.schemas import (
    CandidateProfile,
    JobDescription,
    TailoredCoverLetter,
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


_PROHIBITED_PHRASES = [
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
]

_ALIGNMENT_SCHEMA_HINT = (
    '{"alignment_points": [{"candidate_evidence": str, "job_requirement": str, "connection_explanation": str}], '
    '"evidence_texts": [str]}'
)


def _build_candidate_snapshot(profile: CandidateProfile, resume: TailoredResume) -> str:
    """Build a compact text summary of candidate background for alignment identification."""
    parts = [f"Name: {profile.name}"]

    for exp in resume.experiences[:3]:
        exp_text = f"\nRole: {exp.role_title} at {exp.company} ({exp.start_date}–{exp.end_date or 'Present'})"
        bullets = " | ".join(tb.text for tb in exp.bullets[:3])
        if bullets:
            exp_text += f"\nHighlights: {bullets}"
        parts.append(exp_text)

    if profile.projects:
        proj_snippet = "; ".join(
            f"{p.name}: {p.description[:100]}" for p in profile.projects[:3]
        )
        parts.append(f"\nProjects: {proj_snippet}")

    if profile.skills:
        skills_str = ", ".join(s.name for s in profile.skills[:15])
        parts.append(f"\nSkills: {skills_str}")

    if profile.education:
        edu = profile.education[0]
        edu_str = f"\nEducation: {edu.degree or ''} {edu.field_of_study or ''} — {edu.institution}"
        parts.append(edu_str)

    return "\n".join(parts)


def _build_jd_snapshot(jd: JobDescription) -> str:
    """Compact representation of job requirements for prompt."""
    parts = [f"Role: {jd.role_title} at {jd.company_name or 'the company'}"]
    required = [r.text for r in jd.requirements if r.is_required][:6]
    if required:
        parts.append("Required: " + " | ".join(required))
    if jd.responsibilities:
        parts.append("Responsibilities: " + " | ".join(jd.responsibilities[:5]))
    kw = [k.term for k in jd.keywords if k.importance >= 2][:8]
    if kw:
        parts.append("Key terms: " + ", ".join(kw))
    return "\n".join(parts)


def _identify_alignment(
    profile: CandidateProfile,
    resume: TailoredResume,
    jd: JobDescription,
) -> tuple[list[dict], list[str]]:
    """Call 1: identify 2-4 genuine alignment points."""
    candidate_snapshot = _build_candidate_snapshot(profile, resume)
    jd_snapshot = _build_jd_snapshot(jd)

    system = (
        "You find genuine, specific connections between a candidate's background and a job.\n"
        "RULES:\n"
        "1. ONLY include connections where candidate_evidence cites something SPECIFIC from their background.\n"
        "2. Reject vague connections ('has relevant experience', 'demonstrates skills').\n"
        "3. Each point must cite a specific project, role, achievement, or quantified result.\n"
        "4. Find 2-4 points — quality over quantity. Stop at 2 if fewer strong connections exist.\n"
        "Respond ONLY with valid JSON matching: " + _ALIGNMENT_SCHEMA_HINT
    )
    user_msg = (
        f"CANDIDATE BACKGROUND:\n{candidate_snapshot}\n\n"
        f"JOB REQUIREMENTS:\n{jd_snapshot}"
    )

    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        return data.get("alignment_points", []), data.get("evidence_texts", [])
    except (json.JSONDecodeError, AttributeError):
        return [], []


def _generate_letter(
    profile: CandidateProfile,
    jd: JobDescription,
    alignment_points: list[dict],
    evidence_texts: list[str],
) -> str:
    """Call 2: generate the cover letter narrative."""
    alignment_summary = "\n".join(
        f"- {ap['candidate_evidence']} → {ap['job_requirement']}: {ap['connection_explanation']}"
        for ap in alignment_points
    )
    evidence_summary = "\n".join(f"- {e}" for e in evidence_texts[:6])

    system = (
        "Write a professional cover letter.\n"
        "RULES:\n"
        "1. Every factual claim must come from the provided alignment points and evidence.\n"
        "2. PROHIBITED phrases: "
        + ", ".join(f'"{p}"' for p in _PROHIBITED_PHRASES)
        + "\n"
        "3. MAX 350 words.\n"
        "4. Structure:\n"
        "   P1 (2-3 sentences): Why this specific role at this specific company — cite JD specifics.\n"
        "   P2 (3-4 sentences): First real example with specific details.\n"
        "   P3 (3-4 sentences): Second real example with specific details.\n"
        "   P4 (1-2 sentences): Brief close — no clichés.\n"
        "5. Write in first person. No salutation, no sign-off — just the body paragraphs.\n"
        "6. Do not include a date or address header."
    )
    user_msg = (
        f"Candidate: {profile.name}\n"
        f"Target role: {jd.role_title} at {jd.company_name or 'the company'}\n\n"
        f"ALIGNMENT POINTS TO USE:\n{alignment_summary}\n\n"
        f"EVIDENCE (verbatim from profile):\n{evidence_summary}"
    )

    resp = _get_client().chat.completions.create(
        model=_QUALITY_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()


def _check_prohibited_phrases(text: str) -> list[str]:
    text_lower = text.lower()
    return [p for p in _PROHIBITED_PHRASES if p in text_lower]


def generate_cover_letter(
    profile: CandidateProfile,
    jd: JobDescription,
    resume: TailoredResume,
) -> TailoredCoverLetter:
    """Generate a grounded, evidence-first cover letter."""
    alignment_points_raw, evidence_texts = _identify_alignment(profile, resume, jd)
    generated_text = _generate_letter(profile, jd, alignment_points_raw, evidence_texts)

    word_count = len(generated_text.split())
    prohibited_found = _check_prohibited_phrases(generated_text)

    validation_flags: list[str] = []
    if word_count > 400:
        validation_flags.append(f"Cover letter is {word_count} words (target: ≤350)")
    if prohibited_found:
        validation_flags.append(f"Generic phrases detected: {', '.join(prohibited_found)}")

    alignment_point_strings = [
        f"{ap.get('candidate_evidence', '')} → {ap.get('job_requirement', '')}"
        for ap in alignment_points_raw
    ]

    return TailoredCoverLetter(
        alignment_points=alignment_point_strings,
        evidence_used=evidence_texts,
        generated_text=generated_text,
        word_count=word_count,
        validation_flags=validation_flags,
    )
