"""
JobDescriptionAnalyzer — LLM extraction → structured JobDescription.
Uses Claude Haiku with tool calling.
"""

from __future__ import annotations

import anthropic

from backend.src.models.schemas import (
    JobDescription,
    KeywordEntry,
    RequirementEntry,
)

_client = anthropic.Anthropic()

_JD_TOOL = {
    "name": "analyze_job_description",
    "description": "Extract structured information from a job description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Company name if present",
            },
            "role_title": {
                "type": "string",
                "description": "The exact job title",
            },
            "seniority_level": {
                "type": "string",
                "description": "e.g. entry, mid, senior, staff, principal, manager",
            },
            "requirements": {
                "type": "array",
                "description": "All requirements listed in the job description",
                "items": {
                    "type": "object",
                    "properties": {
                        "text":        {"type": "string"},
                        "is_required": {
                            "type": "boolean",
                            "description": "True if required/must-have, False if preferred/nice-to-have",
                        },
                        "category": {
                            "type": "string",
                            "description": "technical | experience | education | soft_skill | other",
                        },
                    },
                    "required": ["text", "is_required"],
                },
            },
            "responsibilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Key responsibilities listed in the JD",
            },
            "keywords": {
                "type": "array",
                "description": "Important technical and domain keywords",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "importance": {
                            "type": "integer",
                            "description": "3=appears in title or first paragraph, 2=in requirements section, 1=mentioned once elsewhere",
                        },
                        "first_appears_in": {
                            "type": "string",
                            "description": "title | intro | requirements | responsibilities | other",
                        },
                    },
                    "required": ["term", "importance", "first_appears_in"],
                },
            },
            "cultural_signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Values, culture, or soft-skill signals from the JD (e.g. 'fast-paced', 'collaborative')",
            },
        },
        "required": ["role_title", "requirements", "keywords"],
    },
}

_SYSTEM_PROMPT = """You are an expert at analyzing job descriptions.

RULES:
1. Extract ONLY information present in the job description text.
2. For requirements: mark is_required=true for MUST/required/essential, false for preferred/nice-to-have/plus.
3. For keywords: importance 3 = in job title or first paragraph; 2 = in requirements section; 1 = mentioned once elsewhere.
4. Include technical skills, tools, languages, frameworks, methodologies as keywords.
5. Do not infer or add requirements not stated in the text."""


def analyze_job_description(jd_text: str) -> JobDescription:
    """Extract a structured JobDescription from raw job posting text."""
    response = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        temperature=0,
        system=_SYSTEM_PROMPT,
        tools=[_JD_TOOL],
        tool_choice={"type": "tool", "name": "analyze_job_description"},
        messages=[
            {
                "role": "user",
                "content": f"Analyze this job description:\n\n{jd_text}",
            }
        ],
    )

    data: dict = {}
    for block in response.content:
        if block.type == "tool_use" and block.name == "analyze_job_description":
            data = block.input
            break

    requirements = [
        RequirementEntry(
            text=r["text"],
            is_required=r.get("is_required", True),
            category=r.get("category"),
        )
        for r in data.get("requirements", [])
    ]

    keywords = [
        KeywordEntry(
            term=k["term"],
            importance=k.get("importance", 1),
            first_appears_in=k.get("first_appears_in", "other"),
        )
        for k in data.get("keywords", [])
    ]

    return JobDescription(
        company_name=data.get("company_name"),
        role_title=data.get("role_title", ""),
        seniority_level=data.get("seniority_level", ""),
        requirements=requirements,
        responsibilities=data.get("responsibilities", []),
        keywords=keywords,
        cultural_signals=data.get("cultural_signals", []),
        raw_text=jd_text,
    )
