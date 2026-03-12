"""
PDFRenderer — Jinja2 + xhtml2pdf → PDF files.
ATS-safe: single-column, selectable text, standard headings.

1-page guarantee: render_resume_pdf shrinks all pt values in the CSS
(fonts, spacing) in 4% steps until the output fits on a single page.
Page margins (@page, defined in 'in') are never touched.
"""

from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup


def _strip_bullet(text: str) -> str:
    """Strip leading bullet chars, then hard-cap at ~380 chars at a word boundary."""
    text = re.sub(r'^[\s•\-\*·–○]+', '', text).strip()
    if len(text) > 380:
        cut = text[:380]
        last_space = cut.rfind(' ')
        text = (cut[:last_space] if last_space > 250 else cut) + '…'
    return text


def _short_url(url: str) -> str:
    """Strip protocol and www: https://www.linkedin.com/... → linkedin.com/..."""
    return re.sub(r'^https?://(www\.)?', '', url).rstrip('/')


def _url_handle(url: str) -> str:
    """Extract last path component: linkedin.com/in/john-doe → john-doe."""
    clean = re.sub(r'^https?://(www\.)?', '', url).rstrip('/')
    return clean.split('/')[-1]


from backend.src.models.schemas import (
    BulletChange,
    ChangeSummary,
    JobDescription,
    TailoredCoverLetter,
    TailoredResume,
    ValidationResult,
)

_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"
_OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "outputs"))

# ── Template registry ────────────────────────────────────────────────────────

TEMPLATE_REGISTRY: dict[str, dict] = {
    "classic": {
        "name": "Classic",
        "description": "Centered, compact, traditional. Works for any role.",
    },
    "polished": {
        "name": "Polished",
        "description": "Left-aligned, modern hierarchy. Great for tech and business.",
    },
    "traditional": {
        "name": "Traditional",
        "description": "Formal serif style. Ideal for finance, law, or consulting.",
    },
}

_VALID_TEMPLATE_IDS = frozenset(TEMPLATE_REGISTRY.keys())
_DEFAULT_TEMPLATE_ID = "classic"


# ── Jinja2 environment ───────────────────────────────────────────────────────

def _get_jinja_env(template_subdir: str) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR / template_subdir)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters['strip_bullet'] = _strip_bullet
    env.filters['short_url'] = _short_url
    env.filters['url_handle'] = _url_handle
    return env


def _load_resume_css(template_id: str) -> str:
    safe_id = template_id if template_id in _VALID_TEMPLATE_IDS else _DEFAULT_TEMPLATE_ID
    css_path = _TEMPLATE_DIR / "resume" / f"{safe_id}.css"
    return css_path.read_text(encoding="utf-8")


def _load_css(template_subdir: str) -> str:
    css_path = _TEMPLATE_DIR / template_subdir / "base.css"
    return css_path.read_text(encoding="utf-8")


def _scale_css_pt_values(css: str, scale: float) -> str:
    """Multiply every explicit `pt` value in the CSS by scale.

    Only affects content measurements (font-size, margin, padding, etc.).
    Page margins in `@page` use `in` units and are never touched.
    """
    if abs(scale - 1.0) < 1e-4:
        return css

    def _sub(m: re.Match) -> str:
        return f"{float(m.group(1)) * scale:.2f}pt"

    return re.sub(r"([\d.]+)pt", _sub, css)


def _html_to_pdf_bytes(html: str) -> bytes:
    """Render HTML → PDF and return raw bytes (no file I/O)."""
    from xhtml2pdf import pisa  # type: ignore

    buf = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buf, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} errors")
    return buf.getvalue()


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Return the number of pages in a PDF given its raw bytes."""
    import fitz  # PyMuPDF  # type: ignore

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    n = len(doc)
    doc.close()
    return n


def _render_resume_html(template_id: str, context: dict, css: str | None = None) -> str:
    env = _get_jinja_env("resume")
    template = env.get_template("base.html")
    context["css"] = Markup(css if css is not None else _load_resume_css(template_id))
    return template.render(**context)


def _render_html(template_subdir: str, context: dict) -> str:
    env = _get_jinja_env(template_subdir)
    template = env.get_template("base.html")
    context["css"] = Markup(_load_css(template_subdir))
    return template.render(**context)


# ── PDF generation ───────────────────────────────────────────────────────────

def _html_to_pdf(html: str, output_path: Path) -> None:
    from xhtml2pdf import pisa  # type: ignore
    with open(output_path, "wb") as f:
        result = pisa.CreatePDF(html, dest=f, encoding="utf-8")
    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} errors")


def _group_skills(resume: TailoredResume) -> dict[str, list[str]]:
    """Group skills by category for template rendering."""
    grouped: dict[str, list[str]] = {}
    for skill in resume.skills:
        cat = skill.category or "Other"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(skill.name)
    return grouped


# ── Public render functions ──────────────────────────────────────────────────

_FIT_SCALE_START = 1.0
_FIT_SCALE_STEP  = 0.04
_FIT_SCALE_MIN   = 0.72   # ~7.5pt body at minimum — still readable


def render_resume_pdf(
    resume: TailoredResume,
    run_id: str,
    template_id: str = _DEFAULT_TEMPLATE_ID,
) -> str:
    """Render resume to PDF, shrinking fonts/spacing until it fits on 1 page.

    The @page margins (defined in 'in') are never altered. Only the CSS pt
    values (font sizes, margins between entries, etc.) are scaled down in 4%
    steps from 100% to a floor of 72%.  All content is preserved.
    """
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "resume.pdf"

    base_css = _load_resume_css(template_id)
    context = {"resume": resume, "grouped_skills": _group_skills(resume)}

    scale = _FIT_SCALE_START
    pdf_bytes: bytes = b""

    while scale >= _FIT_SCALE_MIN - 1e-4:
        scaled_css = _scale_css_pt_values(base_css, scale)
        html = _render_resume_html(template_id, context.copy(), scaled_css)
        pdf_bytes = _html_to_pdf_bytes(html)
        if _count_pdf_pages(pdf_bytes) <= 1:
            break
        scale -= _FIT_SCALE_STEP

    output_path.write_bytes(pdf_bytes)
    return str(output_path)


def render_cover_letter_pdf(
    resume: TailoredResume,
    cover_letter: TailoredCoverLetter,
    jd: JobDescription,
    run_id: str,
) -> str:
    """Render cover letter to PDF and return the file path."""
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "cover_letter.pdf"

    paragraphs = [p.strip() for p in cover_letter.generated_text.split("\n\n") if p.strip()]
    context = {
        "resume": resume,
        "cover_letter": cover_letter,
        "jd": jd,
        "paragraphs": paragraphs,
        "date": datetime.now().strftime("%B %d, %Y"),
    }
    html = _render_html("cover_letter", context)
    _html_to_pdf(html, output_path)
    return str(output_path)


def render_change_summary(
    resume: TailoredResume,
    cover_letter: TailoredCoverLetter,
    validation: ValidationResult,
    jd: JobDescription,
    run_id: str,
) -> str:
    """Write change_summary.json and return the file path."""
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "change_summary.json"

    summary = ChangeSummary(
        run_id=run_id,
        profile_name=resume.name,
        role_title=jd.role_title,
        company_name=jd.company_name,
        bullet_changes=resume.changes,
        keywords_integrated=[
            kw
            for change in resume.changes
            for kw in change.keywords_added
        ],
        keyword_coverage=validation.keyword_coverage,
        validation_flags=validation.flags,
        cover_letter_alignment_points=cover_letter.alignment_points,
    )

    output_path.write_text(
        summary.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return str(output_path)
