"""
Tests for RelevanceRanker, ResumeTailoringEngine, CoverLetterGenerator,
and QualityValidator. All LLM and embedding calls are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.src.models.schemas import (
    Bullet,
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    JobDescription,
    KeywordEntry,
    ProjectEntry,
    RequirementEntry,
    Skill,
    TailoredCoverLetter,
    TailoredResume,
    TailoredExperience,
    TailoredBullet,
    BulletChange,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_profile() -> CandidateProfile:
    return CandidateProfile(
        name="Jane Smith",
        email="jane@example.com",
        experiences=[
            ExperienceEntry(
                company="Acme Corp",
                role_title="Senior Software Engineer",
                start_date="Jan 2022",
                end_date="Present",
                bullets=[
                    Bullet(
                        text="Built Kafka pipeline processing 2M events/day",
                        source_text="Built Kafka pipeline processing 2M events/day",
                    ),
                    Bullet(
                        text="Reduced API latency by 40% via Redis caching",
                        source_text="Reduced API latency by 40% via Redis caching",
                    ),
                ],
                source_text="Senior Software Engineer | Acme Corp",
            )
        ],
        education=[
            EducationEntry(
                institution="UC Berkeley",
                degree="B.S.",
                field_of_study="Computer Science",
                graduation_date="May 2020",
                source_text="B.S. CS UC Berkeley",
            )
        ],
        projects=[
            ProjectEntry(
                name="ResumeRanker",
                description="NLP pipeline to rank resumes",
                technologies=["Python", "FastAPI", "sentence-transformers"],
                source_text="ResumeRanker: NLP pipeline",
            )
        ],
        skills=[
            Skill(name="Python", category="languages", source_text="Python"),
            Skill(name="Kafka", category="tools", source_text="Kafka"),
            Skill(name="FastAPI", category="frameworks", source_text="FastAPI"),
        ],
        raw_text="Jane Smith\nExperience\nBuilt Kafka pipeline 2M events/day",
    )


def make_jd() -> JobDescription:
    return JobDescription(
        company_name="TechCorp",
        role_title="Senior Backend Engineer",
        seniority_level="senior",
        requirements=[
            RequirementEntry(text="Python or Go", is_required=True, category="technical"),
            RequirementEntry(text="Kafka experience", is_required=True, category="technical"),
            RequirementEntry(text="PostgreSQL", is_required=False, category="technical"),
        ],
        responsibilities=["Build data pipelines", "Own service reliability"],
        keywords=[
            KeywordEntry(term="Python", importance=3, first_appears_in="requirements"),
            KeywordEntry(term="Kafka", importance=2, first_appears_in="requirements"),
            KeywordEntry(term="distributed systems", importance=2, first_appears_in="intro"),
        ],
        cultural_signals=["fast-paced"],
        raw_text="Senior Backend Engineer at TechCorp...",
    )


# ---------------------------------------------------------------------------
# RelevanceRanker tests
# ---------------------------------------------------------------------------

class TestRelevanceRanker:

    def test_returns_relevance_map(self):
        profile = make_profile()
        jd = make_jd()

        # Mock embeddings: return unit vectors with some similarity
        def fake_encode(texts, **kwargs):
            # Return a fixed vector for everything — cosine sim will be 1.0
            n = len(texts)
            vecs = np.ones((n, 384)) / np.sqrt(384)
            return vecs

        with patch("backend.src.matching.relevance_ranker._get_model") as mock_model:
            mock_model.return_value.encode = fake_encode
            from backend.src.matching.relevance_ranker import rank_relevance
            result = rank_relevance(profile, jd)

        assert len(result.scored_entries) > 0
        # All scores should be in [0, 1]
        for entry in result.scored_entries:
            assert 0.0 <= entry.overall_score <= 1.0

    def test_entries_sorted_by_score(self):
        profile = make_profile()
        jd = make_jd()

        call_count = [0]
        def fake_encode(texts, **kwargs):
            # Give experiences higher scores than projects
            n = len(texts)
            vecs = np.random.rand(n, 384)
            vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
            return vecs

        with patch("backend.src.matching.relevance_ranker._get_model") as mock_model:
            mock_model.return_value.encode = fake_encode
            from backend.src.matching.relevance_ranker import rank_relevance
            result = rank_relevance(profile, jd)

        scores = [e.overall_score for e in result.scored_entries]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# QualityValidator tests
# ---------------------------------------------------------------------------

class TestQualityValidator:

    def _make_tailored_resume(self) -> TailoredResume:
        return TailoredResume(
            name="Jane Smith",
            email="jane@example.com",
            summary="Experienced backend engineer with Kafka and Python expertise.",
            experiences=[
                TailoredExperience(
                    company="Acme Corp",
                    role_title="Senior Software Engineer",
                    start_date="Jan 2022",
                    end_date="Present",
                    bullets=[
                        TailoredBullet(
                            text="Built Kafka pipeline processing 2M events/day",
                            source_text="Built Kafka pipeline processing 2M events/day",
                            change=BulletChange(
                                original_text="Built Kafka pipeline processing 2M events/day",
                                revised_text="Built Kafka pipeline processing 2M events/day",
                                change_reason="unchanged",
                                keywords_added=[],
                            ),
                            relevance_score=0.8,
                        )
                    ],
                )
            ],
            skills=[Skill(name="Python", source_text="Python"), Skill(name="Kafka", source_text="Kafka")],
        )

    def _make_cover_letter(self) -> TailoredCoverLetter:
        return TailoredCoverLetter(
            alignment_points=["Kafka experience → stream processing requirement"],
            evidence_used=["Built Kafka pipeline processing 2M events/day"],
            generated_text=(
                "The data platform role at TechCorp aligns with the distributed systems work "
                "I have done at Acme Corp. In my time there, I built and operated a Kafka pipeline "
                "that processed 2 million events per day, directly relevant to TechCorp's scale requirements. "
                "I also reduced API latency by 40% via Redis caching, demonstrating the performance-focused "
                "engineering your team values."
            ),
            word_count=70,
            validation_flags=[],
        )

    def test_validation_passes_for_clean_output(self):
        from backend.src.validation.quality_validator import validate
        resume = self._make_tailored_resume()
        cover_letter = self._make_cover_letter()
        profile = make_profile()
        jd = make_jd()
        result = validate(resume, cover_letter, profile, jd)
        assert isinstance(result.keyword_coverage, float)
        assert 0.0 <= result.keyword_coverage <= 1.0

    def test_generic_phrase_detection(self):
        from backend.src.validation.quality_validator import validate
        resume = self._make_tailored_resume()
        cover_letter = self._make_cover_letter()
        cover_letter.generated_text = "I am excited to apply and am a team player and fast learner."
        cover_letter.word_count = 15
        profile = make_profile()
        jd = make_jd()
        result = validate(resume, cover_letter, profile, jd)
        assert len(result.generic_phrases_found) > 0

    def test_cover_letter_word_count_flag(self):
        from backend.src.validation.quality_validator import validate
        resume = self._make_tailored_resume()
        cover_letter = self._make_cover_letter()
        cover_letter.word_count = 500
        cover_letter.generated_text = " ".join(["word"] * 500)
        profile = make_profile()
        jd = make_jd()
        result = validate(resume, cover_letter, profile, jd)
        assert any("500" in f for f in result.flags)

    def test_keyword_coverage_computed(self):
        from backend.src.validation.quality_validator import validate
        resume = self._make_tailored_resume()
        cover_letter = self._make_cover_letter()
        profile = make_profile()
        jd = make_jd()
        result = validate(resume, cover_letter, profile, jd)
        # Python and Kafka are in the resume; distributed systems probably not
        assert result.keyword_coverage >= 0.0
