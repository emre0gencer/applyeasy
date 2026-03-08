"""GET /api/status/{run_id} — poll generation progress."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.src.models.schemas import StatusResponse
from backend.src.storage.database import get_db, get_run_record

router = APIRouter()


@router.get("/status/{run_id}", response_model=StatusResponse)
def get_status(run_id: str, db: Session = Depends(get_db)) -> StatusResponse:
    record = get_run_record(db, run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        flags = json.loads(record.validation_flags or "[]")
    except Exception:
        flags = []

    return StatusResponse(
        run_id=run_id,
        status=record.status,
        progress_step=record.progress_step,
        progress_message=record.progress_message,
        validation_flags=flags,
        error_message=record.error_message,
        extraction_confidence=record.extraction_confidence,
    )
