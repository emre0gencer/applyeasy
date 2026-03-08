"""Tests for DocumentIngestionEngine."""

from pathlib import Path

import pytest

from backend.src.ingestion.document_ingestion_engine import ingest_text, ingest_file

FIXTURES = Path(__file__).parent / "fixtures"


def _load_sample_profile() -> str:
    return (FIXTURES / "sample_profile.txt").read_text(encoding="utf-8")


def test_ingest_text_returns_sections():
    text = _load_sample_profile()
    doc = ingest_text(text)
    assert doc.source_format == "text"
    assert doc.extraction_method == "raw_text"
    assert "experience" in doc.sections, f"Sections found: {list(doc.sections.keys())}"
    assert doc.confidence > 0.3


def test_ingest_text_normalizes_line_endings():
    text = "Jane Smith\r\nExperience\r\nSoftware Engineer"
    doc = ingest_text(text)
    assert "\r\n" not in doc.raw_text


def test_ingest_text_detects_education():
    text = _load_sample_profile()
    doc = ingest_text(text)
    assert "education" in doc.sections


def test_ingest_text_detects_skills():
    text = _load_sample_profile()
    doc = ingest_text(text)
    assert "skills" in doc.sections


def test_ingest_text_confidence_reasonable():
    text = _load_sample_profile()
    doc = ingest_text(text)
    assert 0.5 <= doc.confidence <= 1.0


def test_ingest_empty_text_low_confidence():
    doc = ingest_text("   ")
    assert doc.confidence < 0.4


def test_ingest_file_txt_routes_to_text():
    text = _load_sample_profile()
    file_bytes = text.encode("utf-8")
    doc = ingest_file(file_bytes, "profile.txt")
    assert doc.source_format == "text"
    assert doc.extraction_method == "raw_text"


def test_ingest_file_pdf_magic_bytes():
    """Verify that files starting with %PDF are routed to PDF ingestion.
    This test uses a fake PDF header — will fail extraction gracefully."""
    fake_pdf = b"%PDF-1.4 fake content"
    doc = ingest_file(fake_pdf, "fake.pdf")
    assert doc.source_format == "pdf"
    # Should fail gracefully, not crash
    assert doc.confidence == 0.0 or doc.warnings


def test_section_header_case_insensitive():
    text = "Jane Smith\nWORK EXPERIENCE\nEngineer at Corp\nEDUCATION\nBS CS"
    doc = ingest_text(text)
    assert "experience" in doc.sections or "header" in doc.sections
