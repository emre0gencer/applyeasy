"""
CandidateProfileBuilder — LLM extraction → structured CandidateProfile.

Uses Claude Haiku with tool calling to enforce schema constraints.
Every extracted entity MUST reference verbatim source_text.
"""

from __future__ import annotations

import json
import re
from typing import Any

import anthropic

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

_client = anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Tool schemas passed to Claude (one per section type)
# ---------------------------------------------------------------------------

_CONTACT_TOOL = {
    "name": "extract_contact",
    "description": "Extract contact/header information from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name":     {"type": "string", "description": "Full name of the candidate"},
            "email":    {"type": "string", "description": "Email address if present"},
            "phone":    {"type": "string", "description": "Phone number if present"},
            "linkedin": {"type": "string", "description": "LinkedIn URL or handle if present"},
            "location": {"type": "string", "description": "City/State or full address if present"},
            "summary":  {"type": "string", "description": "Summary or objective paragraph if present"},
        },
        "required": ["name"],
    },
}

_EXPERIENCE_TOOL = {
    "name": "extract_experiences",
    "description": "Extract all work experience entries from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company":     {"type": "string"},
                        "role_title":  {"type": "string"},
                        "start_date":  {"type": "string", "description": "Preserve original format exactly"},
                        "end_date":    {"type": "string", "description": "Preserve original format; use 'Present' if current"},
                        "location":    {"type": "string"},
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text":        {"type": "string", "description": "The bullet point text"},
                                    "source_text": {"type": "string", "description": "Verbatim text from source"},
                                },
                                "required": ["text", "source_text"],
                            },
                        },
                        "source_text": {"type": "string", "description": "Full text of this experience entry verbatim from source"},
                    },
                    "required": ["company", "role_title", "start_date", "source_text"],
                },
            }
        },
        "required": ["experiences"],
    },
}

_EDUCATION_TOOL = {
    "name": "extract_education",
    "description": "Extract all education entries from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "education": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "institution":      {"type": "string"},
                        "degree":           {"type": "string"},
                        "field_of_study":   {"type": "string"},
                        "graduation_date":  {"type": "string"},
                        "gpa":              {"type": "string"},
                        "honors":           {"type": "array", "items": {"type": "string"}},
                        "source_text":      {"type": "string"},
                    },
                    "required": ["institution", "source_text"],
                },
            }
        },
        "required": ["education"],
    },
}

_PROJECTS_TOOL = {
    "name": "extract_projects",
    "description": "Extract all project entries from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":         {"type": "string"},
                        "description":  {"type": "string"},
                        "technologies": {"type": "array", "items": {"type": "string"}},
                        "url":          {"type": "string"},
                        "bullets": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text":        {"type": "string"},
                                    "source_text": {"type": "string"},
                                },
                                "required": ["text", "source_text"],
                            },
                        },
                        "source_text": {"type": "string"},
                    },
                    "required": ["name", "description", "source_text"],
                },
            }
        },
        "required": ["projects"],
    },
}

_SKILLS_TOOL = {
    "name": "extract_skills",
    "description": "Extract all skills from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name":        {"type": "string"},
                        "category":    {"type": "string", "description": "e.g. languages, frameworks, tools, soft_skills"},
                        "source_text": {"type": "string"},
                    },
                    "required": ["name", "source_text"],
                },
            }
        },
        "required": ["skills"],
    },
}

_AWARDS_TOOL = {
    "name": "extract_awards",
    "description": "Extract awards, certifications, and honors from resume text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "awards": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string"},
                        "issuer":      {"type": "string"},
                        "date":        {"type": "string"},
                        "description": {"type": "string"},
                        "source_text": {"type": "string"},
                    },
                    "required": ["title", "source_text"],
                },
            }
        },
        "required": ["awards"],
    },
}

_SYSTEM_PROMPT = """You are a conservative data extractor for resumes.

RULES:
1. Return ONLY information explicitly present in the source text.
2. Do NOT add, infer, embellish, or expand any information.
3. Every source_text field MUST contain the verbatim text from the source that backs the extracted data.
4. If a field is absent, omit it or use empty string — do NOT guess.
5. Preserve dates in their original format exactly as written.
6. When extracting bullets, use the exact wording from the resume."""


def _call_extraction_tool(section_text: str, tool: dict) -> dict:
    """Call Claude Haiku with a single extraction tool and return the tool input."""
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": section_text}],
    )
    for block in response.content:
        if block.type == "tool_use" and block.name == tool["name"]:
            return block.input
    return {}


def _extract_contact(header_text: str) -> dict[str, Any]:
    if not header_text.strip():
        return {}
    return _call_extraction_tool(
        f"Extract contact information from this resume header:\n\n{header_text}",
        _CONTACT_TOOL,
    )


def _extract_experiences(experience_text: str) -> list[dict]:
    if not experience_text.strip():
        return []
    result = _call_extraction_tool(
        f"Extract all work experience entries from this text:\n\n{experience_text}",
        _EXPERIENCE_TOOL,
    )
    return result.get("experiences", [])


def _extract_education(education_text: str) -> list[dict]:
    if not education_text.strip():
        return []
    result = _call_extraction_tool(
        f"Extract all education entries from this text:\n\n{education_text}",
        _EDUCATION_TOOL,
    )
    return result.get("education", [])


def _extract_projects(projects_text: str) -> list[dict]:
    if not projects_text.strip():
        return []
    result = _call_extraction_tool(
        f"Extract all project entries from this text:\n\n{projects_text}",
        _PROJECTS_TOOL,
    )
    return result.get("projects", [])


def _extract_skills(skills_text: str) -> list[dict]:
    if not skills_text.strip():
        return []
    result = _call_extraction_tool(
        f"Extract all skills from this text:\n\n{skills_text}",
        _SKILLS_TOOL,
    )
    return result.get("skills", [])


def _extract_awards(awards_text: str) -> list[dict]:
    if not awards_text.strip():
        return []
    result = _call_extraction_tool(
        f"Extract all awards, certifications, and honors from this text:\n\n{awards_text}",
        _AWARDS_TOOL,
    )
    return result.get("awards", [])


def build_candidate_profile(doc: IngestedDocument) -> CandidateProfile:
    """
    Extract a structured CandidateProfile from an IngestedDocument.
    Runs extraction calls in sequence (each is fast on Haiku).
    """
    sections = doc.sections
    raw_text = doc.raw_text

    # Build section texts, falling back to full raw text if section not found
    header_text = sections.get("header", raw_text[:2000])
    experience_text = sections.get("experience", "")
    education_text = sections.get("education", "")
    projects_text = sections.get("projects", "")
    skills_text = sections.get("skills", "")
    awards_text = sections.get("awards", "")
    summary_text = sections.get("summary", "")

    # If no sections were detected, use full text for experience extraction
    if not experience_text and len(sections) <= 1:
        experience_text = raw_text

    contact_data = _extract_contact(header_text)
    experiences_data = _extract_experiences(experience_text)
    education_data = _extract_education(education_text)
    projects_data = _extract_projects(projects_text)
    skills_data = _extract_skills(skills_text)
    awards_data = _extract_awards(awards_text)

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

    # Merge summary from contact extraction or dedicated summary section
    summary = contact_data.get("summary") or summary_text or None

    return CandidateProfile(
        name=contact_data.get("name", ""),
        email=contact_data.get("email"),
        phone=contact_data.get("phone"),
        linkedin=contact_data.get("linkedin"),
        location=contact_data.get("location"),
        summary=summary,
        experiences=experiences,
        education=education,
        projects=projects,
        skills=skills,
        awards=awards,
        source_documents=[doc.source_format],
        extraction_confidence=doc.confidence,
        raw_text=raw_text,
    )
