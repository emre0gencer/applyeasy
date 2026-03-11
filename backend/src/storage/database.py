"""SQLAlchemy models and session management for run state."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, Column, String, Text, Float, Integer, DateTime, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = os.environ.get("DB_PATH", "resume_tool.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    """Stores uploaded profile content."""
    __tablename__ = "sessions"

    session_id = Column(String, primary_key=True)
    raw_text = Column(Text, nullable=False)
    source_format = Column(String, default="text")   # "pdf" | "text"
    created_at = Column(DateTime, default=datetime.utcnow)


class RunRecord(Base):
    """Stores the state of a generation run."""
    __tablename__ = "runs"

    run_id = Column(String, primary_key=True)
    session_id = Column(String, nullable=False)
    status = Column(String, default="pending")         # pending|running|completed|failed
    progress_step = Column(String, default="")
    progress_message = Column(String, default="")
    validation_flags = Column(Text, default="[]")      # JSON list
    extraction_confidence = Column(Float, default=0.0)
    resume_pdf_path = Column(String, nullable=True)
    cover_letter_pdf_path = Column(String, nullable=True)
    summary_path = Column(String, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    job_description = Column(Text, default="")
    keyword_coverage = Column(Float, nullable=True)
    experience_count = Column(Integer, nullable=True)
    raw_suitability_score = Column(Integer, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Migrate existing DBs with new columns (no-op if already present)
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE runs ADD COLUMN keyword_coverage FLOAT",
            "ALTER TABLE runs ADD COLUMN experience_count INTEGER",
            "ALTER TABLE runs ADD COLUMN raw_suitability_score INTEGER",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def create_session_record(db: Session, session_id: str, raw_text: str, source_format: str) -> SessionRecord:
    record = SessionRecord(
        session_id=session_id,
        raw_text=raw_text,
        source_format=source_format,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_session_record(db: Session, session_id: str) -> Optional[SessionRecord]:
    return db.query(SessionRecord).filter(SessionRecord.session_id == session_id).first()


def create_run_record(db: Session, run_id: str, session_id: str, job_description: str) -> RunRecord:
    record = RunRecord(
        run_id=run_id,
        session_id=session_id,
        status="pending",
        progress_step="extracting_profile",
        job_description=job_description,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_run_record(db: Session, run_id: str) -> Optional[RunRecord]:
    return db.query(RunRecord).filter(RunRecord.run_id == run_id).first()


def update_run_progress(
    db: Session,
    run_id: str,
    status: str,
    progress_step: str,
    progress_message: str = "",
    validation_flags: Optional[list[str]] = None,
    extraction_confidence: Optional[float] = None,
    resume_pdf_path: Optional[str] = None,
    cover_letter_pdf_path: Optional[str] = None,
    summary_path: Optional[str] = None,
    error_message: Optional[str] = None,
    keyword_coverage: Optional[float] = None,
    experience_count: Optional[int] = None,
    raw_suitability_score: Optional[int] = None,
) -> None:
    record = db.query(RunRecord).filter(RunRecord.run_id == run_id).first()
    if not record:
        return
    record.status = status
    record.progress_step = progress_step
    record.progress_message = progress_message
    if validation_flags is not None:
        record.validation_flags = json.dumps(validation_flags)
    if extraction_confidence is not None:
        record.extraction_confidence = extraction_confidence
    if resume_pdf_path is not None:
        record.resume_pdf_path = resume_pdf_path
    if cover_letter_pdf_path is not None:
        record.cover_letter_pdf_path = cover_letter_pdf_path
    if summary_path is not None:
        record.summary_path = summary_path
    if error_message is not None:
        record.error_message = error_message
    if keyword_coverage is not None:
        record.keyword_coverage = keyword_coverage
    if experience_count is not None:
        record.experience_count = experience_count
    if raw_suitability_score is not None:
        record.raw_suitability_score = raw_suitability_score
    if status in ("completed", "failed"):
        record.completed_at = datetime.utcnow()
    db.commit()
