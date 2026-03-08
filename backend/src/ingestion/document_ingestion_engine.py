"""
DocumentIngestionEngine — PDF/text extraction and normalization.

Priority: text quality > layout fidelity. We want clean, section-tagged text
that downstream extractors can work with reliably.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class IngestedDocument:
    raw_text: str
    sections: dict[str, str]       # section_header → content
    source_format: str             # "pdf" | "text"
    extraction_method: str         # "pdfplumber" | "pymupdf" | "raw_text"
    confidence: float              # 0.0–1.0 estimate of extraction quality
    warnings: list[str] = field(default_factory=list)


# Section header patterns — ordered from most to least specific
_SECTION_PATTERNS = [
    # Exact matches (case-insensitive)
    r"^(work experience|professional experience|experience)$",
    r"^(education|academic background)$",
    r"^(projects?|personal projects?|side projects?)$",
    r"^(skills?|technical skills?|core competencies)$",
    r"^(awards?|honors?|achievements?|certifications?)$",
    r"^(summary|professional summary|objective|profile)$",
    r"^(publications?|research)$",
    r"^(volunteer|volunteering|community)$",
    r"^(languages?)$",
    r"^(interests?|hobbies)$",
]

_COMPILED_SECTIONS = [re.compile(p, re.IGNORECASE) for p in _SECTION_PATTERNS]

# Canonical name mapping
_SECTION_CANONICAL: dict[str, str] = {
    "work experience": "experience",
    "professional experience": "experience",
    "experience": "experience",
    "education": "education",
    "academic background": "education",
    "projects": "projects",
    "personal projects": "projects",
    "side projects": "projects",
    "project": "projects",
    "skills": "skills",
    "technical skills": "skills",
    "core competencies": "skills",
    "skill": "skills",
    "awards": "awards",
    "honors": "awards",
    "achievements": "awards",
    "certifications": "awards",
    "award": "awards",
    "summary": "summary",
    "professional summary": "summary",
    "objective": "summary",
    "profile": "summary",
    "publications": "publications",
    "research": "publications",
    "volunteer": "volunteer",
    "volunteering": "volunteer",
    "community": "volunteer",
    "languages": "languages",
    "interests": "interests",
    "hobbies": "interests",
}


def _is_section_header(line: str) -> Optional[str]:
    """Return canonical section name if line is a section header, else None."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return None
    # Remove trailing punctuation like colons
    cleaned = stripped.rstrip(":").strip()
    for pattern in _COMPILED_SECTIONS:
        if pattern.match(cleaned):
            key = cleaned.lower()
            return _SECTION_CANONICAL.get(key, key)
    return None


def _split_into_sections(text: str) -> dict[str, str]:
    """Split normalized text into sections keyed by canonical header name."""
    lines = text.splitlines()
    sections: dict[str, str] = {}
    current_section = "header"
    buffer: list[str] = []

    for line in lines:
        header = _is_section_header(line)
        if header:
            if buffer:
                content = "\n".join(buffer).strip()
                if content:
                    sections[current_section] = content
            current_section = header
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        content = "\n".join(buffer).strip()
        if content:
            sections[current_section] = content

    return sections


def _normalize_text(text: str) -> str:
    """Normalize whitespace while preserving line structure."""
    # Replace Windows-style line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse more than 3 consecutive blank lines to 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    # Remove trailing whitespace per line
    lines = [line.rstrip() for line in text.splitlines()]
    return "\n".join(lines)


def _extract_with_pdfplumber(file_bytes: bytes) -> tuple[str, str]:
    """Extract text using pdfplumber. Returns (text, method_name)."""
    import pdfplumber  # type: ignore

    pages_text: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if page_text:
                pages_text.append(page_text)
    return "\n\n".join(pages_text), "pdfplumber"


def _extract_with_pymupdf(file_bytes: bytes) -> tuple[str, str]:
    """Fallback extraction using PyMuPDF (fitz)."""
    import fitz  # type: ignore  # PyMuPDF

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages_text: list[str] = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()
    return "\n\n".join(pages_text), "pymupdf"


def _estimate_confidence(text: str, sections: dict[str, str]) -> float:
    """Heuristic confidence score for extraction quality."""
    if not text or len(text) < 100:
        return 0.1
    score = 0.5
    # Bonus for having multiple recognized sections
    score += min(len(sections) * 0.05, 0.3)
    # Bonus for having experience or education
    if "experience" in sections:
        score += 0.1
    if "education" in sections:
        score += 0.05
    # Penalty for very short text
    if len(text) < 500:
        score -= 0.2
    return round(min(max(score, 0.0), 1.0), 2)


def ingest_pdf(file_bytes: bytes, filename: str = "") -> IngestedDocument:
    """Extract and normalize text from a PDF file."""
    warnings: list[str] = []
    raw_text = ""
    method = ""

    try:
        raw_text, method = _extract_with_pdfplumber(file_bytes)
    except Exception as e:
        warnings.append(f"pdfplumber failed ({e}), trying PyMuPDF")
        try:
            raw_text, method = _extract_with_pymupdf(file_bytes)
        except Exception as e2:
            warnings.append(f"PyMuPDF also failed ({e2})")
            return IngestedDocument(
                raw_text="",
                sections={},
                source_format="pdf",
                extraction_method="failed",
                confidence=0.0,
                warnings=warnings,
            )

    if not raw_text.strip():
        warnings.append("PDF produced no extractable text — may be image-based or scanned")
        return IngestedDocument(
            raw_text="",
            sections={},
            source_format="pdf",
            extraction_method=method,
            confidence=0.0,
            warnings=warnings,
        )

    normalized = _normalize_text(raw_text)
    sections = _split_into_sections(normalized)
    confidence = _estimate_confidence(normalized, sections)

    if confidence < 0.4:
        warnings.append(f"Low extraction confidence ({confidence:.2f}) — consider pasting text directly")

    return IngestedDocument(
        raw_text=normalized,
        sections=sections,
        source_format="pdf",
        extraction_method=method,
        confidence=confidence,
        warnings=warnings,
    )


def ingest_text(raw_text: str) -> IngestedDocument:
    """Normalize and section-split pasted plain text."""
    normalized = _normalize_text(raw_text)
    sections = _split_into_sections(normalized)
    confidence = _estimate_confidence(normalized, sections)
    warnings: list[str] = []
    if confidence < 0.4:
        warnings.append("Could not detect standard resume sections — extraction may be less accurate")
    return IngestedDocument(
        raw_text=normalized,
        sections=sections,
        source_format="text",
        extraction_method="raw_text",
        confidence=confidence,
        warnings=warnings,
    )


def ingest_file(file_bytes: bytes, filename: str) -> IngestedDocument:
    """Route to correct ingestion method based on file extension / magic bytes."""
    name_lower = filename.lower()
    is_pdf = name_lower.endswith(".pdf") or file_bytes[:4] == b"%PDF"
    if is_pdf:
        return ingest_pdf(file_bytes, filename)
    # Treat as plain text
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1", errors="replace")
    return ingest_text(text)
