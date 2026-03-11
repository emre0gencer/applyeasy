"""
PDFRenderer — Jinja2 + xhtml2pdf → PDF files.
ATS-safe: single-column, selectable text, standard headings.
"""

from __future__ import annotations

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


def _render_resume_html(template_id: str, context: dict) -> str:
    env = _get_jinja_env("resume")
    template = env.get_template("base.html")
    context["css"] = Markup(_load_resume_css(template_id))
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

def render_resume_pdf(
    resume: TailoredResume,
    run_id: str,
    template_id: str = _DEFAULT_TEMPLATE_ID,
) -> str:
    """Render resume to PDF using the specified template. Returns file path."""
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "resume.pdf"

    html = _render_resume_html(
        template_id,
        {"resume": resume, "grouped_skills": _group_skills(resume)},
    )
    _html_to_pdf(html, output_path)
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
