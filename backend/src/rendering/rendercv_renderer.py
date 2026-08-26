"""RenderCV/Typst rendering path.

Replaces the xhtml2pdf engine, whose limits shaped the output more than any
prompt did: no flexbox (hence float hacks in the template), `letter-spacing`
silently discarded (`getSize: Not a float '0.05em'`), and no real page fitting,
so `_scale_css_pt_values` multiplied every pt value in the CSS by one factor
down to a 72% floor. Typography became a function of content volume — measured
across five fixtures, xhtml2pdf rendered body text at 9.0pt, 7.42pt and 6.95pt
and the candidate's own name at 17pt, 14.02pt and 13.13pt.

This path holds 10pt body / 20pt name across all of them by fitting in a
different order: reclaim whitespace, then margins, then body text in small
steps, and only then remove content. The name and section titles never shrink.

Content is expressed as a RenderCV model (Pydantic, same as our schemas) and
compiled by Typst, which ships as a bundled binary — no LaTeX, no system deps.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.src.models.schemas import TailoredResume
from backend.src.normalization.dates import parse_date
from backend.src.normalization.skills import normalize_skills, order_skill_groups

# ── Design baseline ─────────────────────────────────────────────────────────
# RenderCV's stock classic theme is a CV design: 0.7in margins, a 30pt name,
# generous leading. A strong one-page US resume is denser than that. These
# values are the calibrated starting point; the ladder below only departs from
# them when the content does not fit.

BASE_DESIGN: dict = {
    "theme": "classic",
    "page": {
        "size": "us-letter",
        "top_margin": "0.5in", "bottom_margin": "0.5in",
        "left_margin": "0.5in", "right_margin": "0.5in",
        # Both are CV conventions that do not belong on a job resume.
        "show_footer": False, "show_top_note": False,
    },
    "colors": {
        "name": "black", "headline": "black", "connections": "black",
        "section_titles": "black", "links": "black",
    },
    "typography": {
        "line_spacing": "0.55em",
        "font_size": {"body": "10pt", "name": "20pt", "connections": "9pt"},
    },
    "section_titles": {"space_above": "0.35cm", "space_below": "0.2cm"},
    "sections": {
        "space_between_regular_entries": "0.7em",
        # "4 years 2 months" under every role is a CV habit, not a resume one.
        "show_time_spans_in": [],
    },
}

# RenderCV's stock month abbreviations mix widths ("Jan", "June", "Sept"), which
# reintroduces exactly the date drift `normalization.dates` exists to remove.
LOCALE: dict = {
    "language": "english",
    "present": "Present",
    "month_abbreviations": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}

# Each rung is a named design change, in the order a designer would try them.
# The first rung that fits on one page wins, so a resume that already fits is
# rendered once, at full size, and nothing is touched.
FIT_LADDER: list[tuple[str, dict]] = [
    ("baseline", {}),
    ("tighten-spacing", {
        "typography": {"line_spacing": "0.5em"},
        "sections": {"space_between_regular_entries": "0.55em"},
        "section_titles": {"space_above": "0.28cm", "space_below": "0.16cm"},
    }),
    ("tighten-margins", {
        "page": {"top_margin": "0.4in", "bottom_margin": "0.4in",
                 "left_margin": "0.42in", "right_margin": "0.42in"},
        "typography": {"line_spacing": "0.5em"},
        "sections": {"space_between_regular_entries": "0.5em"},
        "section_titles": {"space_above": "0.25cm", "space_below": "0.15cm"},
    }),
    ("body-9.5pt", {
        "page": {"top_margin": "0.4in", "bottom_margin": "0.4in",
                 "left_margin": "0.42in", "right_margin": "0.42in"},
        "typography": {"line_spacing": "0.48em", "font_size": {"body": "9.5pt"}},
        "sections": {"space_between_regular_entries": "0.45em"},
        "section_titles": {"space_above": "0.22cm", "space_below": "0.14cm"},
    }),
    ("body-9pt", {
        "page": {"top_margin": "0.38in", "bottom_margin": "0.38in",
                 "left_margin": "0.4in", "right_margin": "0.4in"},
        "typography": {"line_spacing": "0.45em", "font_size": {"body": "9pt"}},
        "sections": {"space_between_regular_entries": "0.4em"},
        "section_titles": {"space_above": "0.2cm", "space_below": "0.12cm"},
    }),
]

# Below 9pt body / 0.38in margins a resume stops reading as a designed document.
# Content is trimmed instead of shrinking further.
FLOOR_RUNG = FIT_LADDER[-1][0]

_MIN_BULLETS_PER_EXPERIENCE = 2
_MIN_PROJECTS = 1
_MAX_TRIMS = 8

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


# ── TailoredResume → RenderCV ───────────────────────────────────────────────

def _exact_date(raw: str | None) -> str | None:
    """Render as RenderCV's exact-date format (YYYY, YYYY-MM) or 'present'.

    Returns None for seasons and unparseable text, which the caller routes to
    the free-text `date` field instead — RenderCV rejects anything else.
    """
    if not raw:
        return None
    parsed = parse_date(raw)
    if parsed.is_present:
        return "present"
    if parsed.year is None or parsed.season:
        return None
    if parsed.month:
        return f"{parsed.year:04d}-{parsed.month:02d}"
    return str(parsed.year)


def _range_dates(start: str | None, end: str | None) -> dict:
    """Date fields for a range entry (experience).

    A `start_date` with no `end_date` reads as ongoing to RenderCV, so a range
    is only emitted when both endpoints are known.
    """
    iso_start, iso_end = _exact_date(start), _exact_date(end)
    if iso_start and iso_end:
        return {"start_date": iso_start, "end_date": iso_end}
    if start and end:
        return {"date": f"{parse_date(start).render()} - {parse_date(end).render()}"}
    return _point_date(start)


def _point_date(value: str | None) -> dict:
    """Date fields for a point-in-time entry (graduation, project).

    Always the free-text `date` field: a lone graduation date in `start_date`
    renders as "May 2022 - present".
    """
    return {"date": parse_date(value).render()} if value else {}


def _valid_email(email: str | None) -> str | None:
    """RenderCV validates emails; a malformed one would fail the whole render."""
    return email if email and _EMAIL_RE.fullmatch(email) else None


def _handle(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def build_sections(resume: TailoredResume) -> dict[str, list]:
    """Map a TailoredResume onto RenderCV's section/entry vocabulary."""
    sections: dict[str, list] = {}

    if resume.summary:
        sections["Summary"] = [resume.summary]          # a bare str is a TextEntry

    if resume.experiences:
        sections["Experience"] = [
            {
                "company": exp.company,
                "position": exp.role_title,
                "location": exp.location,
                "highlights": [tb.text for tb in exp.bullets],
                **_range_dates(exp.start_date, exp.end_date),
            }
            for exp in resume.experiences
        ]

    if resume.education:
        sections["Education"] = [
            {
                "institution": edu.institution,
                "area": edu.field_of_study or "",
                "degree": edu.degree,
                "highlights": [h for h in (
                    f"GPA: {edu.gpa}" if edu.gpa else None,
                    ", ".join(edu.honors) if edu.honors else None,
                    f"Relevant Coursework: {edu.coursework}" if edu.coursework else None,
                ) if h],
                **_point_date(edu.graduation_date),
            }
            for edu in resume.education
        ]

    grouped: dict[str, list[str]] = {}
    for skill in normalize_skills(resume.skills):
        grouped.setdefault(skill.category or "Other", []).append(skill.name)
    if grouped:
        sections["Technical Skills"] = [
            {"label": category, "details": ", ".join(names)}
            for category, names in order_skill_groups(grouped).items()
        ]

    if resume.projects:
        sections["Selected Projects"] = [
            {
                "name": proj.name + (f" — {', '.join(proj.technologies[:3])}"
                                     if proj.technologies else ""),
                "highlights": [b.text for b in proj.bullets[:3]] or None,
                "summary": None if proj.bullets else (proj.description or None),
                **_point_date(proj.date),
            }
            for proj in resume.projects
        ]

    # Same merge rule as the xhtml2pdf path: an award already named in a
    # leadership line is a duplicate, not a second item.
    leadership = [{"bullet": item.strip()} for item in resume.leadership_items if item.strip()]
    for award in resume.awards:
        title = (award.title or "").strip()
        if not title or any(title.lower() in i["bullet"].lower() for i in leadership):
            continue
        text = f"**{title}**"
        if award.issuer:
            text += f" — {award.issuer}"
        if award.date:
            text += f" ({award.date})"
        leadership.append({"bullet": text})
    if leadership:
        sections["Leadership & Awards"] = leadership

    return sections


def to_rendercv_model(resume: TailoredResume, design: dict | None = None):
    """Build a validated RenderCVModel from a TailoredResume."""
    from rendercv.schema.models.rendercv_model import RenderCVModel

    social = []
    if resume.linkedin:
        social.append({"network": "LinkedIn", "username": _handle(resume.linkedin)})
    if resume.github:
        social.append({"network": "GitHub", "username": _handle(resume.github)})

    cv = {
        "name": resume.name,
        "location": resume.location,
        "email": _valid_email(resume.email),
        "social_networks": social or None,
        "sections": build_sections(resume),
    }
    return RenderCVModel(
        cv={k: v for k, v in cv.items() if v is not None},
        design=design or BASE_DESIGN,
        locale=LOCALE,
        settings={"pdf_title": f"{resume.name} - Resume"},
    )


# ── Fitting ─────────────────────────────────────────────────────────────────

def deep_merge(base: dict, patch: dict) -> dict:
    """Merge a ladder patch over the baseline without mutating either."""
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def trim_once(resume: TailoredResume) -> tuple[TailoredResume, str] | None:
    """Remove the single least valuable piece of content, or None at the floor.

    Bullets carry `relevance_score`, so "least valuable" is measured rather than
    guessed. Trailing projects go first, then the lowest-scoring bullet from
    whichever entry has the most to spare, then trailing experience entries.
    """
    if len(resume.projects) > _MIN_PROJECTS:
        dropped = resume.projects[-1].name
        return (resume.model_copy(update={"projects": resume.projects[:-1]}),
                f"dropped project '{dropped}'")

    spare = [(i, e) for i, e in enumerate(resume.experiences)
             if len(e.bullets) > _MIN_BULLETS_PER_EXPERIENCE]
    if spare:
        index, entry = max(spare, key=lambda pair: len(pair[1].bullets))
        worst = min(range(len(entry.bullets)),
                    key=lambda b: entry.bullets[b].relevance_score)
        kept = [b for j, b in enumerate(entry.bullets) if j != worst]
        experiences = list(resume.experiences)
        experiences[index] = entry.model_copy(update={"bullets": kept})
        return (resume.model_copy(update={"experiences": experiences}),
                f"dropped lowest-relevance bullet from '{entry.role_title}'")

    if len(resume.experiences) > 2:
        dropped = resume.experiences[-1].role_title
        return (resume.model_copy(update={"experiences": resume.experiences[:-1]}),
                f"dropped experience '{dropped}'")
    return None


def _compile_pdf(model, work_dir: Path) -> bytes:
    """Render the model to Typst source and compile it to PDF bytes."""
    import typst
    from rendercv.renderer.typst import render_full_template

    work_dir.mkdir(parents=True, exist_ok=True)
    typ_path = work_dir / "resume.typ"
    typ_path.write_text(render_full_template(model, "typst"), encoding="utf-8")
    return typst.compile(str(typ_path))


def _page_count(pdf_bytes: bytes) -> int:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count


class FitResult:
    """Outcome of a fitted render: the bytes plus why they look the way they do."""

    def __init__(self, pdf_bytes: bytes, rung: str, renders: int,
                 trims: list[str], fitted: bool):
        self.pdf_bytes = pdf_bytes
        self.rung = rung
        self.renders = renders
        self.trims = trims
        self.fitted = fitted

    def __repr__(self) -> str:
        return (f"FitResult(rung={self.rung!r}, renders={self.renders}, "
                f"trims={len(self.trims)}, fitted={self.fitted})")


def render_fitted(resume: TailoredResume, work_dir: Path,
                  max_trims: int = _MAX_TRIMS) -> FitResult:
    """Render at the largest ladder rung that fits on one page.

    Ordered to keep the common case at a single render:

    1. Try the baseline. Most resumes fit at full size and stop here.
    2. Otherwise jump straight to the floor to answer one question — is this a
       typography problem or a content problem? Trim only while the floor itself
       overflows.
    3. With the content known to fit at the floor, walk the ladder from the top
       and take the largest rung that fits.

    Re-walking the whole ladder after each trim costs O(trims x rungs) renders
    (measured at 25 on a five-experience resume); this ordering is
    O(trims + rungs) and measured at 10 for the same input.
    """
    trims: list[str] = []
    renders = 0

    def render_at(res: TailoredResume, patch: dict) -> bytes:
        nonlocal renders
        renders += 1
        return _compile_pdf(to_rendercv_model(res, deep_merge(BASE_DESIGN, patch)), work_dir)

    baseline_name, baseline_patch = FIT_LADDER[0]
    pdf_bytes = render_at(resume, baseline_patch)
    if _page_count(pdf_bytes) <= 1:
        return FitResult(pdf_bytes, baseline_name, renders, trims, True)

    floor_patch = FIT_LADDER[-1][1]
    current = resume
    for _ in range(max_trims + 1):
        pdf_bytes = render_at(current, floor_patch)
        if _page_count(pdf_bytes) <= 1:
            break
        trimmed = trim_once(current)
        if trimmed is None:
            return FitResult(pdf_bytes, f"{FLOOR_RUNG} (floor)", renders, trims, False)
        current, what = trimmed
        trims.append(what)
    else:
        return FitResult(pdf_bytes, f"{FLOOR_RUNG} (trim budget)", renders, trims, False)

    floor_bytes = pdf_bytes
    for rung, patch in FIT_LADDER[:-1]:
        candidate = render_at(current, patch)
        if _page_count(candidate) <= 1:
            return FitResult(candidate, rung, renders, trims, True)
    return FitResult(floor_bytes, FLOOR_RUNG, renders, trims, True)


def render_resume_pdf_rendercv(resume: TailoredResume, run_id: str,
                               output_dir: Path) -> tuple[str, FitResult]:
    """Public entry point: write resume.pdf for a run and report how it fitted."""
    run_dir = output_dir / run_id
    result = render_fitted(resume, run_dir)
    pdf_path = run_dir / "resume.pdf"
    pdf_path.write_bytes(result.pdf_bytes)
    return str(pdf_path), result
