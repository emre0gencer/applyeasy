"""
CandidateProfileBuilder — LLM extraction → structured CandidateProfile.

Uses Groq (llama-3.1-8b-instant) with JSON mode to enforce schema constraints.
Merges 6 extraction calls into 2 to stay within free-tier RPM limits.
Every extracted entity MUST reference verbatim source_text.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from groq import Groq

from backend.src.models.schemas import (
    AwardEntry,
    Bullet,
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    ProjectEntry,
    Skill,
)
from backend.src.ingestion.document_ingestion_engine import IngestedDocument

_client: "Groq | None" = None

_FAST_MODEL = "llama-3.1-8b-instant"


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


_SYSTEM_PROMPT = """You are a professional data extractor. The input may be a formatted resume, \
a freeform dump of professional/academic background, LinkedIn-style text, project notes, \
or any combination. Your job is to identify and extract structured information regardless of format.

RULES:
1. Return ONLY information explicitly present in the source text.
2. Do NOT add, infer, embellish, or expand any information.
3. Every source_text field MUST contain the verbatim text from the source that backs the extracted data.
4. If a field is absent, omit it or use empty string — do NOT guess.
5. Preserve dates in their original format exactly as written.
6. For experiences: treat any role, job, internship, or position as an experience entry.
7. For projects: treat any described project, side project, or academic project as a project entry.
8. For skills: extract any mentioned technology, language, tool, framework, or skill.
9. When extracting bullets/descriptions, use the exact wording from the source."""


def _call_extraction(system: str, user_msg: str, schema_hint: str) -> dict:
    """Call Groq with JSON mode and return parsed dict."""
    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
        messages=[
            {
                "role": "system",
                "content": system + "\nRespond ONLY with valid JSON matching: " + schema_hint,
            },
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        return json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError):
        return {}


_CORE_SCHEMA_HINT = (
    '{"contact": {"name": str, "email": str, "phone": str, "linkedin": str, "github": str, "location": str, "summary": str}, '
    '"experiences": [{"company": str, "role_title": str, "start_date": str, "end_date": str, '
    '"location": str, "bullets": [{"text": str, "source_text": str}], "source_text": str}], '
    '"education": [{"institution": str, "degree": str, "field_of_study": str, '
    '"graduation_date": str, "gpa": str, "honors": [str], '
    '"coursework": str, "source_text": str}]}'
)

_SUPPLEMENTAL_SCHEMA_HINT = (
    '{"projects": [{"name": str, "description": str, "technologies": [str], "url": str, "date": str, '
    '"bullets": [{"text": str, "source_text": str}], "source_text": str}], '
    '"skills": [{"name": str, "category": str, "source_text": str}], '
    '"awards": [{"title": str, "issuer": str, "date": str, "description": str, "source_text": str}], '
    '"leadership_items": [str]}'
)
# leadership_items: flat single-string descriptions of leadership roles, awards, hackathon results,
# language proficiencies, and notable activities — each a complete standalone bullet sentence.


def _extract_core(raw_text: str) -> dict:
    """Single call: extract contact info, experiences, and education from any input format."""
    user_msg = (
        "Extract all contact information, work experiences, and education entries "
        "from the following text. The text may be a resume, freeform background dump, "
        "or any combination of professional/academic information.\n\n"
        f"{raw_text}"
    )
    return _call_extraction(_SYSTEM_PROMPT, user_msg, _CORE_SCHEMA_HINT)


def _extract_supplemental(raw_text: str) -> dict:
    """Single call: extract projects, skills, and awards from any input format."""
    user_msg = (
        "Extract all projects, skills/technologies, and awards/certifications "
        "from the following text. The text may be a resume, freeform background dump, "
        "or any combination of professional/academic information.\n\n"
        f"{raw_text}"
    )
    return _call_extraction(_SYSTEM_PROMPT, user_msg, _SUPPLEMENTAL_SCHEMA_HINT)


_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+/?",
    re.IGNORECASE,
)
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?",
    re.IGNORECASE,
)


def _scan_links(raw_text: str) -> tuple[str | None, str | None]:
    """Regex scan for LinkedIn and GitHub URLs in raw text. Returns (linkedin, github)."""
    linkedin = next(iter(_LINKEDIN_RE.findall(raw_text)), None)
    github = next(iter(_GITHUB_RE.findall(raw_text)), None)
    return linkedin, github


def build_candidate_profile(doc: IngestedDocument) -> CandidateProfile:
    """
    Extract a structured CandidateProfile from an IngestedDocument.
    Accepts any format: resume, freeform professional/academic dump, or mixed.
    Uses 2 batched LLM calls — both receive the full raw text for maximum coverage.
    Links (LinkedIn, GitHub) are also detected via regex as a reliable fallback.
    """
    raw_text = doc.raw_text
    summary_text = doc.sections.get("summary", "")

    core = _extract_core(raw_text)
    supplemental = _extract_supplemental(raw_text)

    contact_data: dict[str, Any] = core.get("contact", {})

    # Regex link detection — fills in what the LLM may have missed
    regex_linkedin, regex_github = _scan_links(raw_text)
    if not contact_data.get("linkedin") and regex_linkedin:
        contact_data["linkedin"] = regex_linkedin
    if not contact_data.get("github") and regex_github:
        contact_data["github"] = regex_github
    experiences_data: list[dict] = core.get("experiences", [])
    education_data: list[dict] = core.get("education", [])
    projects_data: list[dict] = supplemental.get("projects", [])
    skills_data: list[dict] = supplemental.get("skills", [])
    awards_data: list[dict] = supplemental.get("awards", [])
    leadership_items: list[str] = [s for s in supplemental.get("leadership_items", []) if isinstance(s, str) and s.strip()]

    # Build Pydantic models
    experiences = []
    for exp in experiences_data:
        bullets = [
            Bullet(text=b["text"], source_text=b["source_text"])
            for b in exp.get("bullets", [])
        ]
        experiences.append(ExperienceEntry(
            company=exp.get("company", ""),
            role_title=exp.get("role_title", ""),
            start_date=exp.get("start_date", ""),
            end_date=exp.get("end_date"),
            location=exp.get("location"),
            bullets=bullets,
            source_text=exp.get("source_text", ""),
        ))

    education = [
        EducationEntry(
            institution=e.get("institution", ""),
            degree=e.get("degree"),
            field_of_study=e.get("field_of_study"),
            graduation_date=e.get("graduation_date"),
            gpa=e.get("gpa"),
            honors=e.get("honors", []),
            coursework=e.get("coursework"),
            source_text=e.get("source_text", ""),
        )
        for e in education_data
    ]

    projects = []
    for p in projects_data:
        bullets = [
            Bullet(text=b["text"], source_text=b["source_text"])
            for b in p.get("bullets", [])
        ]
        projects.append(ProjectEntry(
            name=p.get("name", ""),
            description=p.get("description", ""),
            technologies=p.get("technologies", []),
            url=p.get("url"),
            date=p.get("date"),
            bullets=bullets,
            source_text=p.get("source_text", ""),
        ))

    skills = [
        Skill(
            name=s.get("name", ""),
            category=s.get("category"),
            source_text=s.get("source_text", ""),
        )
        for s in skills_data
    ]

    awards = [
        AwardEntry(
            title=a.get("title", ""),
            issuer=a.get("issuer"),
            date=a.get("date"),
            description=a.get("description"),
            source_text=a.get("source_text", ""),
        )
        for a in awards_data
    ]

    summary = contact_data.get("summary") or summary_text or None

    return CandidateProfile(
        name=contact_data.get("name", ""),
        email=contact_data.get("email"),
        phone=contact_data.get("phone"),
        linkedin=contact_data.get("linkedin"),
        github=contact_data.get("github"),
        location=contact_data.get("location"),
        summary=summary,
        experiences=experiences,
        education=education,
        projects=projects,
        skills=skills,
        awards=awards,
        leadership_items=leadership_items,
        source_documents=[doc.source_format],
        extraction_confidence=doc.confidence,
        raw_text=raw_text,
    )
