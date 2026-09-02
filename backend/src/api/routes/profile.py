"""Normalize, review, and save a browser-owned candidate profile."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.src.api.ownership import owns
from backend.src.extraction.candidate_profile_builder import build_candidate_profile
from backend.src.ingestion.document_ingestion_engine import ingest_text
from backend.src.models.schemas import (
    CandidateProfile,
    ProfileNormalizeRequest,
    ProfileReviewResponse,
    ProfileUpdateRequest,
    ProfileUpdateResponse,
)
from backend.src.normalization.profile_review import (
    detect_profile_gaps,
    normalize_profile,
    profile_to_canonical_text,
)
from backend.src.pipeline.errors import ProfileExtractionError
from backend.src.pipeline.profiles import get_pipeline_profile
from backend.src.storage.database import get_db, get_session_record, save_profile_review

router = APIRouter()


def _owned_session(db: Session, session_id: str, request: Request):
    session = get_session_record(db, session_id)
    if not session or not owns(session.owner_id, request):
        raise HTTPException(status_code=404, detail="Session not found. Upload your profile first.")
    return session


@router.post("/profile/{session_id}/normalize", response_model=ProfileReviewResponse)
async def normalize_session_profile(
    session_id: str,
    body: ProfileNormalizeRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ProfileReviewResponse:
    session = _owned_session(db, session_id, request)
    if session.normalized_profile:
        profile = CandidateProfile.model_validate_json(session.normalized_profile)
        gaps = detect_profile_gaps(profile)
        return ProfileReviewResponse(session_id=session_id, profile=profile, gaps=gaps)
    try:
        pipeline_profile = get_pipeline_profile(body.tier)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        profile = await run_in_threadpool(
            build_candidate_profile,
            ingest_text(session.raw_text),
            pipeline_profile.extraction_model,
        )
    except ProfileExtractionError as exc:
        raise HTTPException(status_code=422, detail=exc.public_message) from exc
    profile = normalize_profile(profile)
    gaps = detect_profile_gaps(profile)
    save_profile_review(
        db,
        session_id,
        profile.model_dump_json(),
        json.dumps([gap.model_dump() for gap in gaps]),
    )
    return ProfileReviewResponse(session_id=session_id, profile=profile, gaps=gaps)


@router.put("/profile/{session_id}", response_model=ProfileUpdateResponse)
def update_session_profile(
    session_id: str,
    body: ProfileUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ProfileUpdateResponse:
    _owned_session(db, session_id, request)
    profile = normalize_profile(body.profile)
    canonical_text = profile_to_canonical_text(profile)
    if len(canonical_text) < 30:
        raise HTTPException(status_code=422, detail="Profile is too incomplete to save.")
    # User-confirmed edits become the new evidence source for downstream extraction.
    profile = profile.model_copy(update={"raw_text": canonical_text})
    gaps = detect_profile_gaps(profile)
    save_profile_review(
        db,
        session_id,
        profile.model_dump_json(),
        json.dumps([gap.model_dump() for gap in gaps]),
        raw_text=canonical_text,
    )
    return ProfileUpdateResponse(session_id=session_id, profile=profile, gaps=gaps)
