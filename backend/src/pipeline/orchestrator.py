"""
PipelineOrchestrator — coordinates the full generation run.
Runs as a FastAPI BackgroundTask. Updates SQLite run state at each step.
"""

from __future__ import annotations

import json
import traceback
from typing import Optional

from sqlalchemy.orm import Session

from backend.src.analysis.job_description_analyzer import analyze_job_description
from backend.src.extraction.candidate_profile_builder import build_candidate_profile
from backend.src.generation.cover_letter_generator import generate_cover_letter
from backend.src.generation.resume_tailoring_engine import tailor_resume
from backend.src.ingestion.document_ingestion_engine import ingest_text
from backend.src.matching.relevance_ranker import rank_relevance
from backend.src.models.schemas import PROGRESS_MESSAGES, TailoredCoverLetter

from backend.src.rendering.pdf_renderer import (
    render_change_summary,
    render_cover_letter_pdf,
    render_resume_pdf,
)
from backend.src.storage.database import SessionLocal, get_run_record, update_run_progress
from backend.src.validation.quality_validator import compute_raw_suitability, validate


def _step(
    db: Session,
    run_id: str,
    step: str,
    *,
    status: str = "running",
) -> None:
    update_run_progress(
        db,
        run_id,
        status=status,
        progress_step=step,
        progress_message=PROGRESS_MESSAGES.get(step, step),
    )


def run_pipeline(run_id: str, raw_text: str, job_description: str, template_id: str = "classic", include_cover_letter: bool = False) -> None:
    """
    Full generation pipeline. Called as a background task.
    Uses its own DB session (background tasks don't share the request session).
    """
    db = SessionLocal()
    try:
        _execute_pipeline(db, run_id, raw_text, job_description, template_id, include_cover_letter)
    except Exception as exc:
        tb = traceback.format_exc()
        update_run_progress(
            db,
            run_id,
            status="failed",
            progress_step="failed",
            progress_message="Pipeline failed",
            error_message=f"{exc}\n\n{tb}",
        )
    finally:
        db.close()


def _execute_pipeline(
    db: Session,
    run_id: str,
    raw_text: str,
    job_description: str,
    template_id: str = "classic",
    include_cover_letter: bool = False,
) -> None:
    # ── Step 1: Extract candidate profile ──────────────────────────────────
    _step(db, run_id, "extracting_profile")
    doc = ingest_text(raw_text)
    profile = build_candidate_profile(doc)
    update_run_progress(
        db,
        run_id,
        status="running",
        progress_step="extracting_profile",
        progress_message=PROGRESS_MESSAGES["extracting_profile"],
        extraction_confidence=doc.confidence,
    )

    # ── Step 2: Analyze job description ────────────────────────────────────
    _step(db, run_id, "analyzing_job")
    jd = analyze_job_description(job_description)

    # ── Step 3: Score relevance ─────────────────────────────────────────────
    _step(db, run_id, "scoring_relevance")
    relevance_map = rank_relevance(profile, jd)
    # Persist raw suitability immediately — frontend shows this as the "before" baseline
    raw_score = compute_raw_suitability(profile, jd)
    update_run_progress(
        db, run_id,
        status="running",
        progress_step="scoring_relevance",
        progress_message=PROGRESS_MESSAGES["scoring_relevance"],
        raw_suitability_score=raw_score,
        experience_count=len(profile.experiences),
    )

    # ── Step 4: Tailor resume ───────────────────────────────────────────────
    _step(db, run_id, "tailoring_resume")
    tailored_resume = tailor_resume(profile, jd, relevance_map, raw_score=raw_score)
    # Persist partial score data immediately so the frontend can animate
    # the match score counter before the full pipeline completes.
    update_run_progress(
        db, run_id,
        status="running",
        progress_step="tailoring_resume",
        progress_message=PROGRESS_MESSAGES["tailoring_resume"],
        keyword_coverage=tailored_resume.keyword_coverage,
        experience_count=len(profile.experiences),
    )

    # ── Step 5: Generate cover letter (only if requested) ──────────────────
    if include_cover_letter:
        _step(db, run_id, "generating_cover_letter")
        cover_letter = generate_cover_letter(profile, jd, tailored_resume)
    else:
        cover_letter = TailoredCoverLetter()

    # ── Step 6: Validate ────────────────────────────────────────────────────
    validation = validate(tailored_resume, cover_letter, profile, jd)

    # ── Step 7: Render PDFs ─────────────────────────────────────────────────
    _step(db, run_id, "rendering_pdfs")
    resume_path = render_resume_pdf(tailored_resume, run_id, template_id)
    cl_path = None
    if include_cover_letter:
        cl_path = render_cover_letter_pdf(tailored_resume, cover_letter, jd, run_id)
    summary_path = render_change_summary(tailored_resume, cover_letter, validation, jd, run_id)

    # ── Complete ─────────────────────────────────────────────────────────────
    update_run_progress(
        db,
        run_id,
        status="completed",
        progress_step="completed",
        progress_message="Done",
        validation_flags=validation.flags,
        extraction_confidence=doc.confidence,
        resume_pdf_path=resume_path,
        cover_letter_pdf_path=cl_path,
        summary_path=summary_path,
        keyword_coverage=validation.keyword_coverage,
        experience_count=len(profile.experiences),
    )
