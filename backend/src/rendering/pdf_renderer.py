"""
PDFRenderer — Jinja2 + WeasyPrint → PDF files.
ATS-safe: single-column, selectable text, standard headings.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

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


def _get_jinja_env(template_subdir: str) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR / template_subdir)),
        autoescape=select_autoescape(["html"]),
    )


def _load_css(template_subdir: str) -> str:
    css_path = _TEMPLATE_DIR / template_subdir / "base.css"
    return css_path.read_text(encoding="utf-8")


def _render_html(template_subdir: str, context: dict) -> str:
    env = _get_jinja_env(template_subdir)
    template = env.get_template("base.html")
    context["css"] = _load_css(template_subdir)
    return template.render(**context)


def _html_to_pdf(html: str, output_path: Path) -> None:
    try:
        from weasyprint import HTML  # type: ignore
        HTML(string=html).write_pdf(str(output_path))
    except ImportError:
        raise RuntimeError(
            "WeasyPrint is not installed. Install it with: pip install weasyprint"
        )


def _group_skills(resume: TailoredResume) -> dict[str, list[str]]:
    """Group skills by category for template rendering."""
    grouped: dict[str, list[str]] = {}
    for skill in resume.skills:
        cat = skill.category or "Other"
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(skill.name)
    return grouped


def render_resume_pdf(resume: TailoredResume, run_id: str) -> str:
    """Render resume to PDF and return the file path."""
    output_dir = _OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "resume.pdf"

    html = _render_html("resume", {"resume": resume, "grouped_skills": _group_skills(resume)})
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

    # Split generated text into paragraphs
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
