"""All Pydantic models for the AI Resume & Cover Letter Tailoring System."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


# ---------------------------------------------------------------------------
# Candidate Profile models
# ---------------------------------------------------------------------------

class Bullet(BaseModel):
    text: str
    source_text: str  # verbatim from source — non-negotiable
    relevance_scores: dict[str, float] = {}


class ExperienceEntry(BaseModel):
    company: str
    role_title: str
    start_date: str          # preserve original format exactly
    end_date: Optional[str] = None
    location: Optional[str] = None
    bullets: list[Bullet] = []
    source_text: str = ""    # full section text for entity validation


class EducationEntry(BaseModel):
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    graduation_date: Optional[str] = None
    gpa: Optional[str] = None
    honors: list[str] = []
    coursework: Optional[str] = None   # e.g. "15-122, 67-262, 10-301"
    source_text: str = ""


class ProjectEntry(BaseModel):
    name: str
    description: str
    technologies: list[str] = []
    url: Optional[str] = None
    date: Optional[str] = None        # year or date string
    bullets: list[Bullet] = []
    source_text: str = ""


class Skill(BaseModel):
    name: str
    category: Optional[str] = None   # e.g. "languages", "frameworks", "tools"
    source_text: str = ""


class AwardEntry(BaseModel):
    title: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    source_text: str = ""


class CandidateProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    location: Optional[str] = None
    summary: Optional[str] = None
    experiences: list[ExperienceEntry] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    skills: list[Skill] = []
    awards: list[AwardEntry] = []
    leadership_items: list[str] = []  # flat strings: "VP, Club (2022-24): Led X..."
    source_documents: list[str] = []
    extraction_confidence: float = 0.0   # 0.0–1.0, surfaced in UI
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Job Description models
# ---------------------------------------------------------------------------

class RequirementEntry(BaseModel):
    text: str
    is_required: bool = True
    category: Optional[str] = None   # e.g. "technical", "experience", "soft_skill"


class KeywordEntry(BaseModel):
    term: str
    importance: int                   # 1=low, 2=medium, 3=high
    first_appears_in: str             # "title"|"intro"|"requirements"|"responsibilities"


class JobDescription(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: Optional[str] = None
    role_title: str = ""
    requirements: list[RequirementEntry] = []
    responsibilities: list[str] = []
    keywords: list[KeywordEntry] = []
    cultural_signals: list[str] = []
    seniority_level: str = ""
    raw_text: str = ""


# ---------------------------------------------------------------------------
# Relevance ranking
# ---------------------------------------------------------------------------

class ScoredBullet(BaseModel):
    bullet: Bullet
    relevance_score: float
    matching_keywords: list[str] = []


class ScoredEntry(BaseModel):
    entry_type: str   # "experience" | "project" | "education"
    entry_index: int  # index into profile list
    overall_score: float
    scored_bullets: list[ScoredBullet] = []


class ExperienceRelevanceMap(BaseModel):
    scored_entries: list[ScoredEntry] = []
    job_id: str = ""
    profile_id: str = ""


# ---------------------------------------------------------------------------
# Tailored resume / cover letter
# ---------------------------------------------------------------------------

class BulletChange(BaseModel):
    original_text: str
    revised_text: str
    change_reason: str     # "keyword_integration" | "reorder" | "unchanged"
    keywords_added: list[str] = []


class TailoredBullet(BaseModel):
    text: str
    source_text: str
    change: BulletChange
    relevance_score: float = 0.0


class TailoredExperience(BaseModel):
    company: str
    role_title: str
    start_date: str
    end_date: Optional[str] = None
    location: Optional[str] = None
    bullets: list[TailoredBullet] = []


class TailoredResume(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    location: Optional[str] = None
    summary: str = ""
    experiences: list[TailoredExperience] = []
    education: list[EducationEntry] = []
    projects: list[ProjectEntry] = []
    skills: list[Skill] = []
    awards: list[AwardEntry] = []
    leadership_items: list[str] = []  # flat strings for Leadership & Awards section
    keyword_coverage: float = 0.0     # fraction of high-importance JD keywords present
    changes: list[BulletChange] = []  # full audit trail


class TailoredCoverLetter(BaseModel):
    alignment_points: list[str] = []  # the specific connections found
    evidence_used: list[str] = []     # source_text values used as grounding
    generated_text: str = ""
    word_count: int = 0
    validation_flags: list[str] = []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationResult(BaseModel):
    passed: bool = True
    flags: list[str] = []
    keyword_coverage: float = 0.0
    keywords_present: list[str] = []
    keywords_missing: list[str] = []
    resume_page_estimate: float = 0.0
    cover_letter_word_count: int = 0
    generic_phrases_found: list[str] = []
    hallucination_warnings: list[str] = []


# ---------------------------------------------------------------------------
# Change summary (downloadable JSON)
# ---------------------------------------------------------------------------

class ChangeSummary(BaseModel):
    run_id: str
    profile_name: str
    role_title: str
    company_name: Optional[str] = None
    bullet_changes: list[BulletChange] = []
    keywords_integrated: list[str] = []
    keyword_coverage: float = 0.0
    validation_flags: list[str] = []
    cover_letter_alignment_points: list[str] = []
    generated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ---------------------------------------------------------------------------
# API request/response schemas
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    session_id: str
    message: str = "Profile received"
    detected_format: str = ""    # "pdf" | "text"


class GenerateRequest(BaseModel):
    session_id: str
    job_description: str
    template_id: str = "classic"
    include_cover_letter: bool = False


class GenerateResponse(BaseModel):
    run_id: str
    message: str = "Generation started"


class StatusResponse(BaseModel):
    run_id: str
    status: str      # "pending" | "running" | "completed" | "failed"
    progress_step: str
    progress_message: str = ""
    validation_flags: list[str] = []
    error_message: Optional[str] = None
    extraction_confidence: Optional[float] = None
    keyword_coverage: Optional[float] = None
    experience_count: Optional[int] = None
    raw_suitability_score: Optional[int] = None


# ---------------------------------------------------------------------------
# Pipeline / storage
# ---------------------------------------------------------------------------

PROGRESS_STEPS = [
    "extracting_profile",
    "analyzing_job",
    "scoring_relevance",
    "tailoring_resume",
    "generating_cover_letter",
    "rendering_pdfs",
    "completed",
]

PROGRESS_MESSAGES: dict[str, str] = {
    "extracting_profile":       "Extracting your profile...",
    "analyzing_job":            "Analyzing job description...",
    "scoring_relevance":        "Scoring experience relevance...",
    "tailoring_resume":         "Tailoring resume...",
    "generating_cover_letter":  "Drafting cover letter...",
    "rendering_pdfs":           "Rendering PDFs...",
    "completed":                "Done",
}
