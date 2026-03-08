"""
CoverLetterGenerator — evidence-first LLM narrative generation.
Two-call chain: alignment identification (Sonnet, temp=0) → generation (Sonnet, temp=0.4).
"""

from __future__ import annotations

import re

import anthropic

from backend.src.models.schemas import (
    CandidateProfile,
    JobDescription,
    TailoredCoverLetter,
    TailoredResume,
)

_client = anthropic.Anthropic()

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

_ALIGNMENT_TOOL = {
    "name": "identify_alignment",
    "description": "Identify strong genuine connections between candidate background and job requirements.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alignment_points": {
                "type": "array",
                "description": "2-4 strongest genuine connections. Each must cite specific evidence from candidate background.",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_evidence": {
                            "type": "string",
                            "description": "Specific experience, project, or achievement from candidate background",
                        },
                        "job_requirement": {
                            "type": "string",
                            "description": "The specific job requirement or responsibility this connects to",
                        },
                        "connection_explanation": {
                            "type": "string",
                            "description": "Why this is a genuine connection (1 sentence)",
                        },
                    },
                    "required": ["candidate_evidence", "job_requirement", "connection_explanation"],
                },
                "minItems": 2,
                "maxItems": 4,
            },
            "evidence_texts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verbatim source_text values from candidate profile used as evidence",
            },
        },
        "required": ["alignment_points", "evidence_texts"],
    },
}


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
        "4. Find 2-4 points — quality over quantity. Stop at 2 if fewer strong connections exist."
    )
    user_msg = (
        f"CANDIDATE BACKGROUND:\n{candidate_snapshot}\n\n"
        f"JOB REQUIREMENTS:\n{jd_snapshot}"
    )

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0,
        system=system,
        tools=[_ALIGNMENT_TOOL],
        tool_choice={"type": "tool", "name": "identify_alignment"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "identify_alignment":
            data = block.input
            return data.get("alignment_points", []), data.get("evidence_texts", [])

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

    response = _client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0.4,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return response.content[0].text.strip()


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
