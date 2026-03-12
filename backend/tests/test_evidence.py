"""
Tests for v2 evidence-grounded improvements:
  - EvidenceExtractor heuristics
  - compute_raw_suitability_v2 multi-factor scoring
  - New validation checks (resume generic phrases, redundancy, evidence thinness, robustness)
  - RelevanceRanker bullet_contribution_score
"""

from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import patch

from backend.src.models.schemas import (
    Bullet,
    BulletChange,
    BulletEvidence,
    CandidateProfile,
    ExperienceEntry,
    ExperienceRelevanceMap,
    JobDescription,
    KeywordEntry,
    RequirementEntry,
    ScoredBullet,
    ScoredEntry,
    Skill,
    TailoredBullet,
    TailoredCoverLetter,
    TailoredExperience,
    TailoredResume,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jd(
    must_have: list[str] | None = None,
    preferred: list[str] | None = None,
    domain_signals: list[str] | None = None,
    evidence_style: str = "",
) -> JobDescription:
    return JobDescription(
        company_name="TestCo",
        role_title="Software Engineer",
        seniority_level="mid",
        requirements=[
            RequirementEntry(text="Python experience", is_required=True),
            RequirementEntry(text="SQL knowledge", is_required=True),
            RequirementEntry(text="Docker preferred", is_required=False),
        ],
        keywords=[
            KeywordEntry(term="Python", importance=3, first_appears_in="title"),
            KeywordEntry(term="SQL", importance=2, first_appears_in="requirements"),
            KeywordEntry(term="Docker", importance=1, first_appears_in="other"),
        ],
        must_have_requirements=must_have or ["Python experience", "SQL knowledge"],
        preferred_requirements=preferred or ["Docker preferred"],
        domain_signals=domain_signals or ["backend API ownership", "database design"],
        evidence_style=evidence_style or "backend engineering with database ownership",
        raw_text="Software Engineer role requiring Python and SQL.",
    )


def _make_profile(raw_text: str = "", experiences: list | None = None) -> CandidateProfile:
    return CandidateProfile(
        name="Test User",
        experiences=experiences or [
            ExperienceEntry(
                company="Acme",
                role_title="Developer",
                start_date="2022",
                bullets=[
                    Bullet(
                        text="Built Python API service with PostgreSQL backend for user data management",
                        source_text="Built Python API service with PostgreSQL backend",
                    )
                ],
                source_text="Developer at Acme",
            )
        ],
        skills=[Skill(name="Python", source_text="Python")],
        raw_text=raw_text or "Built Python API service with PostgreSQL backend for user data management.",
        extraction_confidence=0.8,
    )


def _make_tailored_resume(bullet_text: str = "", original_text: str = "") -> TailoredResume:
    return TailoredResume(
        name="Test User",
        summary="Experienced engineer with Python and SQL skills.",
        experiences=[
            TailoredExperience(
                company="Acme",
                role_title="Developer",
                start_date="2022",
                bullets=[
                    TailoredBullet(
                        text=bullet_text or "Built Python API service with database-backed validation.",
                        source_text="Built Python API service",
                        change=BulletChange(
                            original_text=original_text or "Built Python API service",
                            revised_text=bullet_text or "Built Python API service with database-backed validation.",
                            change_reason="keyword_integration",
                            keywords_added=["Python", "SQL"],
                        ),
                        relevance_score=0.75,
                    )
                ],
            )
        ],
        skills=[Skill(name="Python", source_text="Python")],
    )


# ---------------------------------------------------------------------------
# EvidenceExtractor tests
# ---------------------------------------------------------------------------

class TestEvidenceExtractor:

    def test_extracts_ownership_signals(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Designed and built a REST API service for user authentication.")
        assert "designed" in ev.ownership_signals
        assert "built" in ev.ownership_signals

    def test_extracts_scope_signals(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Implemented an end-to-end production-ready data pipeline.")
        assert "end-to-end" in ev.scope_signals
        assert "production" in ev.scope_signals

    def test_extracts_complexity_signals(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Built schema design with validation logic and API integration for the service.")
        assert "schema design" in ev.complexity_signals
        assert "validation" in ev.complexity_signals
        assert "api integration" in ev.complexity_signals

    def test_extracts_deliverable_signals(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Developed a REST API service backed by a relational database schema.")
        assert any("api" in d or "service" in d or "schema" in d for d in ev.deliverable_signals)

    def test_extracts_explicit_metrics(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Reduced latency by 40% and processed 1000 events daily.")
        assert len(ev.explicit_metrics) >= 2

    def test_evidence_strength_higher_for_rich_bullets(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        rich = extract_evidence(
            "Designed an end-to-end production API service with validation logic "
            "and schema design, reducing latency by 30%."
        )
        sparse = extract_evidence("Worked on the backend project.")
        assert rich.evidence_strength > sparse.evidence_strength

    def test_quantifiable_info_score_higher_for_specific_bullets(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        specific = extract_evidence(
            "Implemented schema design with validation and API integration for multi-step workflow."
        )
        vague = extract_evidence("Helped with engineering work on the project.")
        assert specific.quantifiable_info_score > vague.quantifiable_info_score

    def test_unsupported_claim_risk_for_long_vague_bullet(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        # 50 words, no scope/complexity/metrics/deliverable signals — triggers risk
        long_vague = (
            "Participated in ongoing collaborative efforts to enhance general aspects of "
            "the product quality while helping all team members across many different "
            "areas of concern that were consistently relevant to the broader group "
            "mission and strategic priorities throughout the entire long engagement "
            "period, all in pursuit of organizational goals and shared objectives."
        )
        ev = extract_evidence(long_vague)
        # The condition requires >45 words with no grounding signals
        assert ev.unsupported_claim_risk > 0

    def test_no_unsupported_risk_for_grounded_bullet(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        grounded = extract_evidence(
            "Built a Python API with PostgreSQL-backed validation logic and schema design "
            "for end-to-end user data workflows, processing 50K records daily."
        )
        assert grounded.unsupported_claim_risk == 0.0

    def test_action_is_first_ownership_verb(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Designed and then built the service.")
        assert ev.action == "designed"

    def test_returns_bullet_evidence_instance(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("Built a service.")
        assert isinstance(ev, BulletEvidence)
        assert 0.0 <= ev.evidence_strength <= 1.0
        assert 0.0 <= ev.quantifiable_info_score <= 1.0

    def test_empty_string_does_not_crash(self):
        from backend.src.analysis.evidence_extractor import extract_evidence
        ev = extract_evidence("")
        assert ev.evidence_strength == 0.0


# ---------------------------------------------------------------------------
# compute_raw_suitability_v2 tests
# ---------------------------------------------------------------------------

class TestRawSuitabilityV2:

    def test_returns_tuple_of_int_and_dict(self):
        from backend.src.validation.quality_validator import compute_raw_suitability_v2
        profile = _make_profile()
        jd = _make_jd()
        score, breakdown = compute_raw_suitability_v2(profile, jd)
        assert isinstance(score, int)
        assert isinstance(breakdown, dict)
        assert 0 <= score <= 100

    def test_breakdown_contains_expected_keys(self):
        from backend.src.validation.quality_validator import compute_raw_suitability_v2
        profile = _make_profile()
        jd = _make_jd()
        _, breakdown = compute_raw_suitability_v2(profile, jd)
        for key in ("must_have_coverage", "preferred_coverage", "semantic_relevance",
                    "evidence_quality", "extraction_clarity", "raw_total"):
            assert key in breakdown, f"Missing key: {key}"

    def test_breakdown_values_in_valid_range(self):
        from backend.src.validation.quality_validator import compute_raw_suitability_v2
        profile = _make_profile()
        jd = _make_jd()
        _, breakdown = compute_raw_suitability_v2(profile, jd)
        for key in ("must_have_coverage", "preferred_coverage", "semantic_relevance",
                    "evidence_quality", "extraction_clarity"):
            assert 0.0 <= breakdown[key] <= 1.0, f"{key}={breakdown[key]} out of range"

    def test_must_have_coverage_higher_for_matching_profile(self):
        from backend.src.validation.quality_validator import compute_raw_suitability_v2
        matching = _make_profile(raw_text="Python developer with SQL database experience.")
        no_match = _make_profile(raw_text="Java developer focused on mobile applications.")
        jd = _make_jd()
        _, b1 = compute_raw_suitability_v2(matching, jd)
        _, b2 = compute_raw_suitability_v2(no_match, jd)
        assert b1["must_have_coverage"] >= b2["must_have_coverage"]

    def test_uses_relevance_map_when_provided(self):
        from backend.src.validation.quality_validator import compute_raw_suitability_v2
        from backend.src.analysis.evidence_extractor import extract_evidence
        profile = _make_profile()
        jd = _make_jd()
        evidence = extract_evidence("Built Python API with SQL database schema.")
        scored_bullet = ScoredBullet(
            bullet=profile.experiences[0].bullets[0],
            relevance_score=0.75,
            evidence=evidence,
            bullet_contribution_score=0.65,
        )
        scored_entry = ScoredEntry(
            entry_type="experience",
            entry_index=0,
            overall_score=0.65,
            scored_bullets=[scored_bullet],
        )
        relevance_map = ExperienceRelevanceMap(
            scored_entries=[scored_entry],
            job_id=jd.job_id,
            profile_id=profile.profile_id,
        )
        score_with_map, breakdown_with_map = compute_raw_suitability_v2(profile, jd, relevance_map)
        score_without_map, breakdown_without_map = compute_raw_suitability_v2(profile, jd, None)
        # With a high-scoring relevance map, semantic_relevance should be higher
        assert breakdown_with_map["semantic_relevance"] == pytest.approx(0.65, abs=0.01)

    def test_backward_compat_compute_raw_suitability(self):
        from backend.src.validation.quality_validator import compute_raw_suitability
        profile = _make_profile()
        jd = _make_jd()
        score = compute_raw_suitability(profile, jd)
        assert isinstance(score, int)
        assert 0 <= score <= 100


# ---------------------------------------------------------------------------
# v2 Validation checks
# ---------------------------------------------------------------------------

class TestValidationV2:

    def test_resume_generic_phrase_detection(self):
        from backend.src.validation.quality_validator import _check_resume_generic_phrases
        resume = _make_tailored_resume(
            bullet_text="I am a team player who is highly motivated and detail-oriented."
        )
        found = _check_resume_generic_phrases(resume)
        assert len(found) > 0
        assert any("team player" in p or "highly motivated" in p for p in found)

    def test_resume_no_generic_phrases_for_clean_bullet(self):
        from backend.src.validation.quality_validator import _check_resume_generic_phrases
        resume = _make_tailored_resume(
            bullet_text="Built a Python REST API service with PostgreSQL-backed validation logic."
        )
        found = _check_resume_generic_phrases(resume)
        assert len(found) == 0

    def test_bullet_redundancy_detection(self):
        from backend.src.validation.quality_validator import _check_bullet_redundancy
        bullet_text = "Built Python API with database schema for user authentication service."
        # Create resume with two near-identical bullets
        resume = TailoredResume(
            name="Test",
            summary="",
            experiences=[
                TailoredExperience(
                    company="Acme", role_title="Dev", start_date="2022",
                    bullets=[
                        TailoredBullet(
                            text=bullet_text,
                            source_text="", change=BulletChange(
                                original_text="", revised_text=bullet_text,
                                change_reason="unchanged", keywords_added=[]),
                            relevance_score=0.7,
                        ),
                        TailoredBullet(
                            text=bullet_text + " and data pipeline.",
                            source_text="", change=BulletChange(
                                original_text="", revised_text=bullet_text,
                                change_reason="unchanged", keywords_added=[]),
                            relevance_score=0.7,
                        ),
                    ]
                )
            ],
        )
        flags = _check_bullet_redundancy(resume)
        assert len(flags) > 0

    def test_evidence_thinness_flags_long_vague_bullet(self):
        from backend.src.validation.quality_validator import _check_evidence_quality
        # Must be >50 words with low evidence strength to trigger the thinness flag
        long_vague = (
            "Worked on various engineering tasks and helped the team with multiple "
            "aspects of the project including general development and related activities "
            "that contributed to the overall success of the initiative and team goals "
            "over time, continuously supporting the broader mission of driving better "
            "outcomes through sustained and ongoing collaborative effort across the entire organization."
        )
        resume = _make_tailored_resume(bullet_text=long_vague)
        flags = _check_evidence_quality(resume)
        assert len(flags) > 0

    def test_evidence_thinness_does_not_flag_rich_bullet(self):
        from backend.src.validation.quality_validator import _check_evidence_quality
        rich = (
            "Designed an end-to-end production API service with PostgreSQL schema design "
            "and validation logic, handling user authentication workflows with 50K daily records."
        )
        resume = _make_tailored_resume(bullet_text=rich)
        flags = _check_evidence_quality(resume)
        assert len(flags) == 0

    def test_robustness_flags_keyword_heavy_low_evidence_rewrite(self):
        from backend.src.validation.quality_validator import _check_robustness
        # Original: low evidence. Revised: same evidence but 3+ keywords added.
        original = "Worked on backend project tasks."
        revised = "Worked on Python Django FastAPI REST backend project tasks with Kubernetes Docker."
        resume = TailoredResume(
            name="Test",
            summary="",
            experiences=[
                TailoredExperience(
                    company="Acme", role_title="Dev", start_date="2022",
                    bullets=[
                        TailoredBullet(
                            text=revised,
                            source_text=original,
                            change=BulletChange(
                                original_text=original,
                                revised_text=revised,
                                change_reason="keyword_integration",
                                keywords_added=["Python", "Django", "FastAPI", "Kubernetes"],
                            ),
                            relevance_score=0.6,
                        )
                    ]
                )
            ],
        )
        flags = _check_robustness(resume)
        assert len(flags) > 0

    def test_robustness_does_not_flag_evidence_improving_rewrite(self):
        from backend.src.validation.quality_validator import _check_robustness
        original = "Built API service."
        revised = (
            "Designed a production Python REST API service with PostgreSQL schema design "
            "and validation logic for end-to-end user authentication workflows."
        )
        resume = TailoredResume(
            name="Test",
            summary="",
            experiences=[
                TailoredExperience(
                    company="Acme", role_title="Dev", start_date="2022",
                    bullets=[
                        TailoredBullet(
                            text=revised,
                            source_text=original,
                            change=BulletChange(
                                original_text=original,
                                revised_text=revised,
                                change_reason="keyword_integration",
                                keywords_added=["Python", "PostgreSQL", "REST"],
                            ),
                            relevance_score=0.8,
                        )
                    ]
                )
            ],
        )
        flags = _check_robustness(resume)
        assert len(flags) == 0

    def test_validate_includes_evidence_quality_flags(self):
        from backend.src.validation.quality_validator import validate
        profile = _make_profile()
        jd = _make_jd()
        cover_letter = TailoredCoverLetter()
        long_vague = (
            "Worked on various engineering tasks and contributed to team activities "
            "while helping with multiple aspects of development work over time."
        )
        resume = _make_tailored_resume(bullet_text=long_vague)
        result = validate(resume, cover_letter, profile, jd)
        assert hasattr(result, "evidence_quality_flags")
        assert isinstance(result.evidence_quality_flags, list)

    def test_validate_includes_score_breakdown_when_provided(self):
        from backend.src.validation.quality_validator import validate
        profile = _make_profile()
        jd = _make_jd()
        cover_letter = TailoredCoverLetter()
        resume = _make_tailored_resume()
        breakdown = {"must_have_coverage": 0.8, "semantic_relevance": 0.6}
        result = validate(resume, cover_letter, profile, jd, score_breakdown=breakdown)
        assert result.score_breakdown == breakdown


# ---------------------------------------------------------------------------
# Ranker v2: bullet_contribution_score tests
# ---------------------------------------------------------------------------

class TestRankerV2:

    def _fake_encode(self, texts, **kwargs):
        n = len(texts)
        vecs = np.ones((n, 384)) / np.sqrt(384)
        return vecs

    def test_scored_bullet_has_contribution_score(self):
        profile = _make_profile()
        jd = _make_jd()

        with patch("backend.src.matching.relevance_ranker._get_model") as mock_model:
            mock_model.return_value.encode = self._fake_encode
            from backend.src.matching.relevance_ranker import rank_relevance
            result = rank_relevance(profile, jd)

        for entry in result.scored_entries:
            for sb in entry.scored_bullets:
                assert sb.bullet_contribution_score >= 0.0
                assert sb.bullet_contribution_score <= 1.0

    def test_scored_bullet_has_evidence(self):
        profile = _make_profile()
        jd = _make_jd()

        with patch("backend.src.matching.relevance_ranker._get_model") as mock_model:
            mock_model.return_value.encode = self._fake_encode
            from backend.src.matching.relevance_ranker import rank_relevance
            result = rank_relevance(profile, jd)

        for entry in result.scored_entries:
            for sb in entry.scored_bullets:
                assert sb.evidence is not None
                assert isinstance(sb.evidence, BulletEvidence)

    def test_contribution_score_higher_for_evidence_rich_bullet(self):
        """A bullet with strong evidence signals should outscore a vague bullet
        of similar semantic similarity."""
        from backend.src.matching.relevance_ranker import _score_bullets

        evidence_rich = Bullet(
            text="Designed an end-to-end production API service with PostgreSQL schema design "
                 "and validation logic for user authentication workflows.",
            source_text="",
        )
        evidence_sparse = Bullet(
            text="Worked on backend development tasks.",
            source_text="",
        )

        jd = _make_jd()
        job_vec = np.ones(384) / np.sqrt(384)

        with patch("backend.src.matching.relevance_ranker._embed") as mock_embed:
            # Same cosine similarity for both bullets
            mock_embed.return_value = np.array([job_vec, job_vec])
            scored = _score_bullets([evidence_rich, evidence_sparse], job_vec, jd)

        assert scored[0].bullet_contribution_score > scored[1].bullet_contribution_score
