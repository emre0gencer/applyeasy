"""Canonical profile review document and deterministic gap detection."""

from __future__ import annotations

import re

from backend.src.models.schemas import CandidateProfile, ProfileGap
from backend.src.normalization.ordering import (
    normalize_education,
    normalize_experiences,
    normalize_projects,
)
from backend.src.normalization.skills import normalize_skills


_OUTCOME_RE = re.compile(
    r"(?:\b\d[\d,.]*\s*(?:%|x|ms|s|k|m|million|billion)?\b|"
    r"\b(?:increas|reduc|improv|sav|grew|accelerat|prevent|eliminat|deliver|"
    r"launch|ship|support|serv|enabl|result)\w*\b)",
    re.IGNORECASE,
)


def normalize_profile(profile: CandidateProfile) -> CandidateProfile:
    """Apply deterministic presentation normalization to extracted fields."""
    return profile.model_copy(
        update={
            "experiences": normalize_experiences(profile.experiences),
            "education": normalize_education(profile.education),
            "projects": normalize_projects(profile.projects),
            "skills": normalize_skills(profile.skills),
        }
    )


def detect_profile_gaps(profile: CandidateProfile) -> list[ProfileGap]:
    gaps: list[ProfileGap] = []
    if not profile.name.strip():
        gaps.append(ProfileGap(code="missing_name", path="name", message="Add your name."))
    if not (profile.email or profile.phone or profile.linkedin):
        gaps.append(ProfileGap(
            code="missing_contact",
            path="contact",
            message="Add at least one contact method.",
        ))

    for index, experience in enumerate(profile.experiences):
        base = f"experiences.{index}"
        if not experience.start_date or not experience.end_date:
            gaps.append(ProfileGap(
                code="missing_dates",
                path=f"{base}.dates",
                message=f"Add complete dates for {experience.role_title or experience.company or 'this role'}.",
            ))
        if not experience.bullets:
            gaps.append(ProfileGap(
                code="missing_bullets",
                path=f"{base}.bullets",
                message=f"Add at least one accomplishment for {experience.role_title or experience.company or 'this role'}.",
                severity="error",
            ))
        for bullet_index, bullet in enumerate(experience.bullets):
            if not _OUTCOME_RE.search(bullet.text):
                gaps.append(ProfileGap(
                    code="outcome_missing",
                    path=f"{base}.bullets.{bullet_index}",
                    message="Consider adding a concrete result, scale, or delivered outcome.",
                    severity="info",
                ))
            if not bullet.source_text.strip():
                gaps.append(ProfileGap(
                    code="missing_source",
                    path=f"{base}.bullets.{bullet_index}",
                    message="This bullet has no source evidence; verify or remove it.",
                    severity="error",
                ))

    for index, project in enumerate(profile.projects):
        if not project.date:
            gaps.append(ProfileGap(
                code="missing_project_date",
                path=f"projects.{index}.date",
                message=f"Add a date for {project.name or 'this project'} if available.",
                severity="info",
            ))
        if not project.description and not project.bullets:
            gaps.append(ProfileGap(
                code="missing_project_detail",
                path=f"projects.{index}.description",
                message=f"Add evidence describing {project.name or 'this project'}.",
                severity="warning",
            ))
    return gaps


def profile_to_canonical_text(profile: CandidateProfile) -> str:
    """Serialize user-reviewed fields as the source for downstream extraction."""
    p = normalize_profile(profile)
    lines: list[str] = [p.name.strip()]
    contact = [v.strip() for v in (p.email, p.phone, p.location, p.linkedin, p.github) if v and v.strip()]
    if contact:
        lines.append(" | ".join(contact))
    if p.summary:
        lines.extend(["", "SUMMARY", p.summary.strip()])
    if p.experiences:
        lines.extend(["", "EXPERIENCE"])
        for exp in p.experiences:
            heading = " — ".join(v for v in (exp.role_title.strip(), exp.company.strip()) if v)
            dates = " – ".join(v for v in (exp.start_date, exp.end_date) if v)
            meta = " | ".join(v for v in (dates, exp.location) if v)
            lines.append(heading)
            if meta:
                lines.append(meta)
            lines.extend(f"- {bullet.text.strip()}" for bullet in exp.bullets if bullet.text.strip())
    if p.education:
        lines.extend(["", "EDUCATION"])
        for edu in p.education:
            parts = [edu.institution, edu.degree, edu.field_of_study, edu.graduation_date]
            lines.append(" | ".join(v.strip() for v in parts if v and v.strip()))
            if edu.gpa:
                lines.append(f"GPA: {edu.gpa.strip()}")
            if edu.honors:
                lines.append("Honors: " + "; ".join(edu.honors))
            if edu.coursework:
                lines.append("Coursework: " + edu.coursework.strip())
    if p.projects:
        lines.extend(["", "PROJECTS"])
        for project in p.projects:
            heading = project.name.strip()
            if project.date:
                heading += f" | {project.date.strip()}"
            lines.append(heading)
            if project.technologies:
                lines.append("Technologies: " + ", ".join(project.technologies))
            if project.url:
                lines.append(project.url.strip())
            if project.description:
                lines.append(project.description.strip())
            lines.extend(f"- {bullet.text.strip()}" for bullet in project.bullets if bullet.text.strip())
    if p.skills:
        lines.extend(["", "SKILLS"])
        categories: dict[str, list[str]] = {}
        for skill in p.skills:
            categories.setdefault(skill.category or "Other", []).append(skill.name)
        lines.extend(f"{category}: {', '.join(names)}" for category, names in categories.items())
    if p.awards:
        lines.extend(["", "AWARDS"])
        for award in p.awards:
            parts = [award.title, award.issuer, award.date, award.description]
            lines.append(" | ".join(v.strip() for v in parts if v and v.strip()))
    if p.leadership_items:
        lines.extend(["", "LEADERSHIP"])
        lines.extend(f"- {item.strip()}" for item in p.leadership_items if item.strip())
    return "\n".join(line for line in lines if line is not None).strip()
