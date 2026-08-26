"""Per-tier pipeline configuration.

The profile is selected once at the API boundary and passed through the
orchestrator.  Keeping model and feature choices here prevents tier checks from
spreading across generation modules.
"""

from __future__ import annotations

from dataclasses import dataclass


FAST_MODEL = "llama-3.1-8b-instant"
QUALITY_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class PipelineProfile:
    name: str
    extraction_model: str
    job_analysis_model: str
    bullet_model: str
    project_model: str
    repair_model: str
    repair_enabled: bool
    normalization_enabled: bool
    cover_letter_enabled: bool
    variant_count: int


STANDARD_PROFILE = PipelineProfile(
    name="standard",
    extraction_model=FAST_MODEL,
    job_analysis_model=FAST_MODEL,
    bullet_model=QUALITY_MODEL,
    project_model=FAST_MODEL,
    repair_model=QUALITY_MODEL,
    repair_enabled=False,
    normalization_enabled=True,
    cover_letter_enabled=False,
    variant_count=1,
)

PRO_PROFILE = PipelineProfile(
    name="pro",
    extraction_model=QUALITY_MODEL,
    job_analysis_model=QUALITY_MODEL,
    bullet_model=QUALITY_MODEL,
    project_model=QUALITY_MODEL,
    repair_model=QUALITY_MODEL,
    repair_enabled=True,
    normalization_enabled=True,
    cover_letter_enabled=True,
    variant_count=3,
)

_PROFILES = {
    STANDARD_PROFILE.name: STANDARD_PROFILE,
    PRO_PROFILE.name: PRO_PROFILE,
}


def get_pipeline_profile(tier: str) -> PipelineProfile:
    """Return the named profile; reject unknown tiers instead of guessing."""
    try:
        return _PROFILES[tier.strip().lower()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"Unsupported pipeline tier: {tier!r}") from exc
