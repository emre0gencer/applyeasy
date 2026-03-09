"""
JobDescriptionAnalyzer — LLM extraction → structured JobDescription.
Uses Groq (llama-3.1-8b-instant) with JSON mode.
"""

from __future__ import annotations

import json
import os

from groq import Groq

from backend.src.models.schemas import (
    JobDescription,
    KeywordEntry,
    RequirementEntry,
)

_client: "Groq | None" = None

_FAST_MODEL = "llama-3.1-8b-instant"


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


_SCHEMA_HINT = (
    '{"company_name": str, "role_title": str, "seniority_level": str, '
    '"requirements": [{"text": str, "is_required": bool, "category": str}], '
    '"responsibilities": [str], '
    '"keywords": [{"term": str, "importance": int, "first_appears_in": str}], '
    '"cultural_signals": [str]}'
)

_SYSTEM_PROMPT = (
    "You are an expert at analyzing job descriptions.\n\n"
    "RULES:\n"
    "1. Extract ONLY information present in the job description text.\n"
    "2. For requirements: mark is_required=true for MUST/required/essential, false for preferred/nice-to-have/plus.\n"
    "3. For keywords: importance 3 = in job title or first paragraph; 2 = in requirements section; 1 = mentioned once elsewhere.\n"
    "4. Include technical skills, tools, languages, frameworks, methodologies as keywords.\n"
    "5. Do not infer or add requirements not stated in the text.\n"
    "Respond ONLY with valid JSON matching: " + _SCHEMA_HINT
)


def analyze_job_description(jd_text: str) -> JobDescription:
    """Extract a structured JobDescription from raw job posting text."""
    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this job description:\n\n{jd_text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data: dict = json.loads(resp.choices[0].message.content)
    except (json.JSONDecodeError, AttributeError):
        data = {}

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
