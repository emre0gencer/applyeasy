"""POST /api/generate — trigger background pipeline, return run_id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.src.models.schemas import GenerateRequest, GenerateResponse
from backend.src.pipeline.orchestrator import run_pipeline
from backend.src.storage.database import create_run_record, get_db, get_session_record

router = APIRouter()


@router.post("/generate", response_model=GenerateResponse)
async def generate_documents(
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GenerateResponse:
    """
    Start the generation pipeline for a given session_id + job_description.
    Returns run_id immediately; poll /status/{run_id} for progress.
    """
    session = get_session_record(db, request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Upload your profile first.")

    jd_text = request.job_description.strip()
    if not jd_text:
        raise HTTPException(status_code=422, detail="Job description cannot be empty.")
    if len(jd_text) < 50:
        raise HTTPException(status_code=422, detail="Job description is too short.")

    run_id = str(uuid.uuid4())
    create_run_record(db, run_id, request.session_id, jd_text)

    # Launch pipeline as a background task
    background_tasks.add_task(run_pipeline, run_id, session.raw_text, jd_text)

    return GenerateResponse(run_id=run_id, message="Generation started")
