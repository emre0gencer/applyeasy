"""POST /api/upload — accept PDF file or raw text, return session_id."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.src.ingestion.document_ingestion_engine import ingest_file, ingest_text
from backend.src.models.schemas import UploadResponse
from backend.src.storage.database import create_session_record, get_db

router = APIRouter()

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/upload", response_model=UploadResponse)
async def upload_profile(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Accept either:
    - A multipart file upload (PDF or .txt)
    - A form field `text` with raw resume content
    Returns session_id for use in /generate.
    """
    if file and file.filename:
        content = await file.read()
        if len(content) > _MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
        doc = ingest_file(content, file.filename)
        raw_text = doc.raw_text
        source_format = doc.source_format
        if not raw_text.strip():
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from the uploaded file. "
                       "Please try pasting your resume as text instead.",
            )
    elif text and text.strip():
        doc = ingest_text(text)
        raw_text = doc.raw_text
        source_format = "text"
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either a file upload or a text body.",
        )

    session_id = str(uuid.uuid4())
    create_session_record(db, session_id, raw_text, source_format)

    return UploadResponse(
        session_id=session_id,
        message="Profile received",
        detected_format=source_format,
    )
