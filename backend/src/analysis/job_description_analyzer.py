"""
JobDescriptionAnalyzer — LLM extraction → structured JobDescription.
Uses Groq (llama-3.1-8b-instant) with JSON mode.

v2: Extended to extract domain_signals, evidence_style, repeated_themes,
    seniority_cues, and pre-populated must_have / preferred requirement lists.
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
    '"cultural_signals": [str], '
    '"domain_signals": [str], '
    '"evidence_style": str, '
    '"repeated_themes": [str], '
    '"seniority_cues": [str]}'
)

_SYSTEM_PROMPT = (
    "You are an expert at analyzing job descriptions.\n\n"
    "RULES:\n"
    "1. Extract ONLY information present in the job description text.\n"
    "2. For requirements: mark is_required=true for MUST/required/essential, false for preferred/nice-to-have/plus.\n"
    "3. For keywords: importance 3 = in job title or first paragraph; 2 = in requirements section; 1 = mentioned once elsewhere.\n"
    "4. Include technical skills, tools, languages, frameworks, methodologies as keywords.\n"
    "5. Do not infer or add requirements not stated in the text.\n"
    "6. domain_signals: 2-5 short phrases describing what kinds of work or evidence the role values most "
    '   (e.g. "backend API ownership", "ML experimentation and evaluation", "production system reliability", '
    '   "data pipeline engineering", "cross-functional delivery"). Infer from responsibilities + requirements.\n'
    "7. evidence_style: one short phrase summarizing the dominant evidence the role rewards "
    '   (e.g. "production backend engineering", "ML experimentation with measurable evaluation", '
    '   "data infrastructure ownership"). Single phrase only.\n'
    "8. repeated_themes: 3-5 themes or concepts that appear across multiple sections of the JD "
    "   (e.g. themes appearing in both responsibilities and requirements).\n"
    "9. seniority_cues: phrases in the JD that indicate expected seniority level "
    '   (e.g. "3+ years", "lead projects", "mentor junior engineers", "independently own").\n'
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

    # Pre-populate must_have / preferred lists from the structured requirements
    must_have = [r.text for r in requirements if r.is_required]
    preferred = [r.text for r in requirements if not r.is_required]

    # v2 fields — fall back gracefully if the model omits them
    domain_signals: list[str] = [
        s for s in data.get("domain_signals", []) if isinstance(s, str) and s.strip()
    ]
    evidence_style: str = (data.get("evidence_style") or "").strip()
    repeated_themes: list[str] = [
        s for s in data.get("repeated_themes", []) if isinstance(s, str) and s.strip()
    ]
    seniority_cues: list[str] = [
        s for s in data.get("seniority_cues", []) if isinstance(s, str) and s.strip()
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
        # v2 fields
        must_have_requirements=must_have,
        preferred_requirements=preferred,
        domain_signals=domain_signals,
        evidence_style=evidence_style,
        repeated_themes=repeated_themes,
        seniority_cues=seniority_cues,
    )
