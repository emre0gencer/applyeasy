"""GET /api/download/{run_id}/{doc} — serve generated files."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.src.storage.database import get_db, get_run_record

router = APIRouter()


def _get_completed_run(run_id: str, db: Session):
    record = get_run_record(db, run_id)
    if not record:
        raise HTTPException(status_code=404, detail="Run not found")
    if record.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Run is not yet completed (status: {record.status})",
        )
    return record


@router.get("/download/{run_id}/resume")
def download_resume(run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    record = _get_completed_run(run_id, db)
    path = record.resume_pdf_path
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Resume PDF not found")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename="resume.pdf",
    )


@router.get("/download/{run_id}/cover-letter")
def download_cover_letter(run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    record = _get_completed_run(run_id, db)
    path = record.cover_letter_pdf_path
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Cover letter PDF not found")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename="cover_letter.pdf",
    )


@router.get("/download/{run_id}/summary")
def download_summary(run_id: str, db: Session = Depends(get_db)) -> FileResponse:
    record = _get_completed_run(run_id, db)
    path = record.summary_path
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Change summary not found")
    return FileResponse(
        path=path,
        media_type="application/json",
        filename="change_summary.json",
    )
