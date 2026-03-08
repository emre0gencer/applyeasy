"""
Tests for CandidateProfileBuilder and JobDescriptionAnalyzer.
These tests mock the Anthropic API to avoid real API calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.src.ingestion.document_ingestion_engine import ingest_text
from backend.src.models.schemas import (
    CandidateProfile,
    JobDescription,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_tool_use_block(name: str, data: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = data
    return block


def _make_response(*blocks) -> MagicMock:
    resp = MagicMock()
    resp.content = list(blocks)
    return resp


# ---------------------------------------------------------------------------
# CandidateProfileBuilder tests
# ---------------------------------------------------------------------------

class TestCandidateProfileBuilder:

    def test_build_profile_structure(self):
        """Profile builder returns a CandidateProfile with expected fields."""
        doc = ingest_text(_load_fixture("sample_profile.txt"))

        contact_block = _make_tool_use_block("extract_contact", {
            "name": "Jane Smith",
            "email": "jane.smith@email.com",
            "phone": "(555) 123-4567",
            "linkedin": "linkedin.com/in/janesmith",
            "location": "San Francisco, CA",
        })
        exp_block = _make_tool_use_block("extract_experiences", {
            "experiences": [
                {
                    "company": "Acme Corp",
                    "role_title": "Senior Software Engineer",
                    "start_date": "Jan 2022",
                    "end_date": "Present",
                    "location": "San Francisco, CA",
                    "bullets": [
                        {"text": "Built Kafka pipeline processing 2M events/day",
                         "source_text": "Built Kafka pipeline processing 2M events/day"},
                    ],
                    "source_text": "Senior Software Engineer | Acme Corp | Jan 2022 – Present",
                }
            ]
        })
        edu_block = _make_tool_use_block("extract_education", {
            "education": [
                {
                    "institution": "University of California, Berkeley",
                    "degree": "B.S.",
                    "field_of_study": "Computer Science",
                    "graduation_date": "May 2020",
                    "gpa": "3.7",
                    "source_text": "B.S. Computer Science | UC Berkeley | May 2020",
                }
            ]
        })
        projects_block = _make_tool_use_block("extract_projects", {"projects": []})
        skills_block = _make_tool_use_block("extract_skills", {
            "skills": [
                {"name": "Python", "category": "languages", "source_text": "Python"},
                {"name": "FastAPI", "category": "frameworks", "source_text": "FastAPI"},
            ]
        })
        awards_block = _make_tool_use_block("extract_awards", {"awards": []})

        responses = [
            _make_response(contact_block),
            _make_response(exp_block),
            _make_response(edu_block),
            _make_response(projects_block),
            _make_response(skills_block),
            _make_response(awards_block),
        ]

        with patch("backend.src.extraction.candidate_profile_builder._client") as mock_client:
            mock_client.messages.create.side_effect = responses
            from backend.src.extraction.candidate_profile_builder import build_candidate_profile
            profile = build_candidate_profile(doc)

        assert isinstance(profile, CandidateProfile)
        assert profile.name == "Jane Smith"
        assert profile.email == "jane.smith@email.com"
        assert len(profile.experiences) == 1
        assert profile.experiences[0].company == "Acme Corp"
        assert len(profile.experiences[0].bullets) == 1
        assert len(profile.education) == 1
        assert len(profile.skills) == 2

    def test_profile_id_is_uuid(self):
        """Profile gets a unique ID."""
        import uuid
        from backend.src.models.schemas import CandidateProfile
        profile = CandidateProfile()
        assert uuid.UUID(profile.profile_id)  # doesn't raise


# ---------------------------------------------------------------------------
# JobDescriptionAnalyzer tests
# ---------------------------------------------------------------------------

class TestJobDescriptionAnalyzer:

    def test_analyze_jd_structure(self):
        """JD analyzer returns structured JobDescription."""
        jd_text = _load_fixture("sample_jd.txt")

        jd_block = _make_tool_use_block("analyze_job_description", {
            "company_name": "TechCorp",
            "role_title": "Senior Backend Engineer",
            "seniority_level": "senior",
            "requirements": [
                {"text": "4+ years of experience", "is_required": True, "category": "experience"},
                {"text": "Python or Go", "is_required": True, "category": "technical"},
                {"text": "Kafka or Kinesis", "is_required": True, "category": "technical"},
                {"text": "Airflow or Spark experience", "is_required": False, "category": "technical"},
            ],
            "responsibilities": [
                "Design data ingestion pipelines",
                "Own reliability of platform services",
            ],
            "keywords": [
                {"term": "Python", "importance": 3, "first_appears_in": "requirements"},
                {"term": "Kafka", "importance": 2, "first_appears_in": "requirements"},
                {"term": "distributed systems", "importance": 2, "first_appears_in": "requirements"},
                {"term": "PostgreSQL", "importance": 2, "first_appears_in": "requirements"},
                {"term": "Docker", "importance": 1, "first_appears_in": "requirements"},
            ],
            "cultural_signals": ["low-ego", "fast-paced"],
        })

        with patch("backend.src.analysis.job_description_analyzer._client") as mock_client:
            mock_client.messages.create.return_value = _make_response(jd_block)
            from backend.src.analysis.job_description_analyzer import analyze_job_description
            jd = analyze_job_description(jd_text)

        assert isinstance(jd, JobDescription)
        assert jd.role_title == "Senior Backend Engineer"
        assert jd.company_name == "TechCorp"
        assert jd.seniority_level == "senior"
        # Check required vs preferred
        required = [r for r in jd.requirements if r.is_required]
        preferred = [r for r in jd.requirements if not r.is_required]
        assert len(required) == 3
        assert len(preferred) == 1
        # Keywords
        high_kw = [k for k in jd.keywords if k.importance >= 2]
        assert len(high_kw) >= 3

    def test_jd_has_raw_text(self):
        """Raw JD text is preserved."""
        jd_text = "Engineer role at Acme"
        jd_block = _make_tool_use_block("analyze_job_description", {
            "role_title": "Engineer",
            "requirements": [],
            "keywords": [],
        })
        with patch("backend.src.analysis.job_description_analyzer._client") as mock_client:
            mock_client.messages.create.return_value = _make_response(jd_block)
            from backend.src.analysis.job_description_analyzer import analyze_job_description
            jd = analyze_job_description(jd_text)
        assert jd.raw_text == jd_text
