from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.src.api.routes import profile as profile_routes
from backend.src.models.schemas import (
    Bullet,
    CandidateProfile,
    ExperienceEntry,
    KeywordEntry,
    ProjectEntry,
    Skill,
)
from backend.src.normalization.keywords import canonicalize_keywords
from backend.src.normalization.profile_review import (
    detect_profile_gaps,
    normalize_profile,
    profile_to_canonical_text,
)


def _request(owner: str | None = None) -> Request:
    headers = []
    if owner:
        headers.append((b"cookie", f"ae_owner={owner}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def _profile() -> CandidateProfile:
    return CandidateProfile(
        name="Ada Lovelace",
        email="ada@example.com",
        experiences=[
            ExperienceEntry(
                company="Analytical Engines",
                role_title="Engineer",
                start_date="June 2022",
                end_date="",
                bullets=[Bullet(text="Designed computation notes", source_text="Designed computation notes")],
                source_text="Engineer at Analytical Engines",
            )
        ],
        projects=[ProjectEntry(name="Engine", description="Built a prototype", source_text="Built a prototype")],
        skills=[
            Skill(name="Python", category="Programming Languages", source_text="Python"),
            Skill(name="python", category="Languages", source_text="python"),
        ],
    )


def test_profile_normalization_and_gap_detection():
    profile = normalize_profile(_profile())
    assert profile.experiences[0].start_date == "Jun 2022"
    assert [skill.name for skill in profile.skills] == ["Python"]

    gaps = detect_profile_gaps(profile)
    assert {gap.code for gap in gaps} >= {
        "missing_dates",
        "outcome_missing",
        "missing_project_date",
    }


def test_reviewed_profile_serializes_as_canonical_source():
    text = profile_to_canonical_text(_profile())
    assert "EXPERIENCE" in text
    assert "Engineer — Analytical Engines" in text
    assert "Jun 2022" in text
    assert "SKILLS\nLanguages: Python" in text


def test_keyword_aliases_collapse_and_keep_strongest_importance():
    keywords = canonicalize_keywords([
        KeywordEntry(term="React.js", importance=1, first_appears_in="responsibilities"),
        KeywordEntry(term="ReactJS", importance=3, first_appears_in="title"),
        KeywordEntry(term="Postgres", importance=2, first_appears_in="requirements"),
        KeywordEntry(term="PostgreSQL", importance=1, first_appears_in="other"),
    ])
    assert [(item.term, item.importance) for item in keywords] == [
        ("React", 3),
        ("PostgreSQL", 2),
    ]


def test_profile_route_hides_another_owners_session(monkeypatch: pytest.MonkeyPatch):
    record = SimpleNamespace(owner_id="owner-a")
    monkeypatch.setattr(profile_routes, "get_session_record", lambda _db, _session_id: record)

    with pytest.raises(HTTPException) as error:
        profile_routes._owned_session(object(), "session-1", _request("owner-b"))
    assert error.value.status_code == 404


def test_profile_route_accepts_matching_owner(monkeypatch: pytest.MonkeyPatch):
    record = SimpleNamespace(owner_id="owner-a")
    monkeypatch.setattr(profile_routes, "get_session_record", lambda _db, _session_id: record)
    assert profile_routes._owned_session(object(), "session-1", _request("owner-a")) is record
