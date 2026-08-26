"""Tests for tier selection and per-tier quality controls."""

import pytest

from backend.src.models.schemas import GenerateRequest
from backend.src.pipeline.profiles import get_pipeline_profile


def test_generate_request_defaults_to_standard():
    request = GenerateRequest(session_id="s", job_description="x" * 60)
    assert request.tier == "standard"


def test_pro_enables_quality_stages_and_models():
    standard = get_pipeline_profile("standard")
    pro = get_pipeline_profile("PRO")

    assert not standard.repair_enabled
    assert pro.repair_enabled
    assert not standard.cover_letter_enabled
    assert pro.cover_letter_enabled
    assert pro.extraction_model != standard.extraction_model
    assert pro.job_analysis_model != standard.job_analysis_model
    assert pro.project_model != standard.project_model


def test_unknown_tier_is_rejected():
    with pytest.raises(ValueError, match="Unsupported pipeline tier"):
        get_pipeline_profile("enterprise")
