"""Regression tests for relevance-ranked, deeper project content."""

from unittest.mock import patch

from backend.src.models.schemas import (
    Bullet,
    CandidateProfile,
    ExperienceRelevanceMap,
    JobDescription,
    ProjectEntry,
    ScoredEntry,
    TailoredCoverLetter,
    TailoredResume,
)
from backend.src.generation.resume_tailoring_engine import (
    _rank_project_candidates,
    tailor_resume,
)


def _project(name: str, bullets: int = 1) -> ProjectEntry:
    return ProjectEntry(
        name=name,
        description=f"{name} service with Python and FastAPI",
        technologies=["Python", "FastAPI"],
        bullets=[
            Bullet(text=f"Implemented {name} service.", source_text=f"Implemented {name} service.")
            for _ in range(bullets)
        ],
        source_text=f"{name} service with Python and FastAPI",
    )


def _relevance(scores: list[float]) -> ExperienceRelevanceMap:
    return ExperienceRelevanceMap(scored_entries=[
        ScoredEntry(entry_type="project", entry_index=index, overall_score=score)
        for index, score in enumerate(scores)
    ])


def test_projects_are_ranked_by_role_relevance():
    profile = CandidateProfile(projects=[_project("First"), _project("Best"), _project("Middle")])
    ranked = _rank_project_candidates(profile, _relevance([0.1, 0.9, 0.5]))
    assert [project.name for project, _score in ranked] == ["Best", "Middle", "First"]


def test_relevant_project_gets_second_bullet_even_when_page_is_full():
    profile = CandidateProfile(name="Jane", projects=[_project("Relevant")])
    relevance = _relevance([0.9])
    jd = JobDescription(role_title="Backend Engineer")
    captured_requests = []

    def generate(requests, _jd, model):
        captured_requests.extend(requests)
        return {
            0: [Bullet(
                text="Architected FastAPI request validation around the supplied Python service boundaries.",
                source_text=profile.projects[0].source_text,
            )]
        }

    with (
        patch(
            "backend.src.generation.resume_tailoring_engine._select_and_tailor_experiences",
            return_value=([], "Backend engineer focused on API delivery. Systems background aligned to the role."),
        ),
        patch(
            "backend.src.generation.resume_tailoring_engine._tailor_projects",
            side_effect=lambda projects, *_args, **_kwargs: (projects, []),
        ),
        patch(
            "backend.src.generation.resume_tailoring_engine._estimate_chars",
            return_value=4000,
        ),
        patch(
            "backend.src.generation.resume_tailoring_engine._generate_extra_project_bullets_batch",
            side_effect=generate,
        ),
    ):
        resume = tailor_resume(profile, jd, relevance)

    assert [(request[0], request[2]) for request in captured_requests] == [(0, 1)]
    assert resume.projects[0].relevance_score == 0.9
    assert len(resume.projects[0].bullets) == 2
    assert resume.changes[-1].change_reason == "project_expansion"


def test_validator_surfaces_unmet_relevant_project_depth():
    from backend.src.validation.quality_validator import validate

    project = _project("Thin")
    project.relevance_score = 0.8
    result = validate(
        TailoredResume(name="Jane", projects=[project]),
        TailoredCoverLetter(),
        CandidateProfile(raw_text=project.source_text),
        JobDescription(),
    )

    assert any("fewer than two" in flag for flag in result.flags)
    assert any("fewer than two" in flag for flag in result.evidence_quality_flags)
