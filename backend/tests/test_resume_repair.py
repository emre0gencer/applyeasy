"""Tests for the single complaint-directed Pro repair call."""

import json
from unittest.mock import MagicMock, patch

from backend.src.generation.resume_repair import repair_resume
from backend.src.models.schemas import (
    Bullet,
    BulletChange,
    CandidateProfile,
    JobDescription,
    ProjectEntry,
    TailoredBullet,
    TailoredExperience,
    TailoredResume,
)


def _response(payload: dict) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = json.dumps(payload)
    return response


def test_repair_fixes_voice_and_adds_missing_relevant_project_bullet():
    original = "Built API endpoints with FastAPI."
    resume = TailoredResume(
        name="Jane Smith",
        summary="Jane Smith builds backend systems. She works with Python.",
        experiences=[TailoredExperience(
            company="Acme",
            role_title="Engineer",
            start_date="2024",
            bullets=[TailoredBullet(
                text=original,
                source_text=original,
                change=BulletChange(
                    original_text=original,
                    revised_text=original,
                    change_reason="unchanged",
                ),
            )],
        )],
        projects=[ProjectEntry(
            name="API Lab",
            description="FastAPI service with request validation",
            technologies=["Python", "FastAPI"],
            bullets=[Bullet(text=original, source_text=original)],
            source_text="FastAPI service with request validation",
            relevance_score=0.8,
        )],
    )
    response = _response({"results": [
        {"id": "summary", "revised_text": "Backend engineer building Python services. Focused on API validation."},
        {"id": "project_new:0:1", "revised_text": "Implemented request validation for the FastAPI service in Python."},
    ]})

    with patch("backend.src.generation.resume_repair._client") as client:
        client.chat.completions.create.return_value = response
        repaired = repair_resume(
            resume,
            CandidateProfile(raw_text="FastAPI service with request validation in Python"),
            JobDescription(role_title="Backend Engineer"),
            ["Summary refers to the candidate in the third person"],
            model="repair-model",
        )

    assert repaired.summary.startswith("Backend engineer")
    assert len(repaired.projects[0].bullets) == 2
    assert repaired.changes[-1].change_reason == "quality_repair"
    assert client.chat.completions.create.call_args.kwargs["model"] == "repair-model"
