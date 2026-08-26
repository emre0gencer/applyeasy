"""One-pass, complaint-directed resume repair for the Pro pipeline."""

from __future__ import annotations

import json
import os

from groq import Groq

from backend.src.analysis.evidence_extractor import extract_evidence
from backend.src.models.schemas import (
    Bullet,
    BulletChange,
    CandidateProfile,
    JobDescription,
    TailoredResume,
)
from backend.src.validation.style_rules import (
    find_generic_phrases,
    find_hedges,
    find_repeated_verbs,
    has_third_person_pronoun,
    opens_with_name,
)

_client: "Groq | None" = None
_QUALITY_MODEL = "llama-3.3-70b-versatile"
_PROJECT_RELEVANCE_THRESHOLD = 0.28


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=30.0, max_retries=2)
    return _client


def _complaints(text: str) -> list[str]:
    issues: list[str] = []
    generic = find_generic_phrases(text)
    hedges = find_hedges(text)
    if generic:
        issues.append(f"remove generic phrases: {', '.join(generic)}")
    if hedges:
        issues.append(f"remove vague quantifiers: {', '.join(hedges)}")
    if len(text.split()) > 50 and extract_evidence(text).evidence_strength < 0.20:
        issues.append("tighten this evidence-thin bullet and foreground concrete supplied details")
    return issues


def _collect_items(
    resume: TailoredResume,
    validation_issues: list[str],
) -> list[dict]:
    """Map deterministic validation complaints to exact editable content."""
    items: list[dict] = []

    summary_issues: list[str] = []
    if opens_with_name(resume.summary, resume.name):
        summary_issues.append("rewrite in implied first person; do not open with the candidate name")
    if has_third_person_pronoun(resume.summary):
        summary_issues.append("remove third-person pronouns")
    if summary_issues:
        items.append({
            "id": "summary",
            "kind": "summary",
            "original": resume.summary,
            "source": resume.summary,
            "complaints": summary_issues,
        })

    repeated_by_exp: dict[int, set[str]] = {}
    for exp_index, exp in enumerate(resume.experiences):
        repeated_by_exp[exp_index] = set(
            find_repeated_verbs([bullet.text for bullet in exp.bullets])
        )

    repeated_by_project: dict[int, set[str]] = {}
    for project_index, project in enumerate(resume.projects):
        repeated_by_project[project_index] = set(
            find_repeated_verbs([bullet.text for bullet in project.bullets])
        )

    all_refs: list[tuple[str, str]] = []
    for exp_index, exp in enumerate(resume.experiences):
        for bullet_index, bullet in enumerate(exp.bullets):
            item_id = f"experience:{exp_index}:{bullet_index}"
            issues = _complaints(bullet.text)
            opening = bullet.text.split(maxsplit=1)[0].strip("•-*.,").lower() if bullet.text else ""
            if opening in repeated_by_exp[exp_index]:
                issues.append("use a different, accurate opening action verb from the other bullets in this role")
            if issues:
                items.append({
                    "id": item_id,
                    "kind": "experience_bullet",
                    "original": bullet.text,
                    "source": bullet.source_text,
                    "complaints": issues,
                })
            all_refs.append((item_id, bullet.text))

    for project_index, project in enumerate(resume.projects):
        for bullet_index, bullet in enumerate(project.bullets):
            item_id = f"project:{project_index}:{bullet_index}"
            issues = _complaints(bullet.text)
            opening = bullet.text.split(maxsplit=1)[0].strip("•-*.,").lower() if bullet.text else ""
            if opening in repeated_by_project[project_index]:
                issues.append("use a distinct, accurate opening verb within this project")
            if issues:
                items.append({
                    "id": item_id,
                    "kind": "project_bullet",
                    "original": bullet.text,
                    "source": bullet.source_text or project.source_text or project.description,
                    "complaints": issues,
                })
            all_refs.append((item_id, bullet.text))

        if (
            project.relevance_score >= _PROJECT_RELEVANCE_THRESHOLD
            and len(project.bullets) < 2
        ):
            for slot in range(len(project.bullets), 2):
                items.append({
                    "id": f"project_new:{project_index}:{slot}",
                    "kind": "new_project_bullet",
                    "original": "",
                    "source": project.source_text or project.description,
                    "project": project.name,
                    "technologies": project.technologies,
                    "existing_bullets": [bullet.text for bullet in project.bullets],
                    "complaints": ["add a distinct second evidence-grounded project bullet"],
                })

    # Attach near-duplicate complaints to the later bullet in each pair.
    item_map = {item["id"]: item for item in items}
    for left in range(len(all_refs)):
        left_words = set(all_refs[left][1].lower().split())
        for right in range(left + 1, len(all_refs)):
            right_words = set(all_refs[right][1].lower().split())
            denominator = min(len(left_words), len(right_words))
            if denominator >= 6 and len(left_words & right_words) / denominator > 0.70:
                right_id, right_text = all_refs[right]
                item = item_map.get(right_id)
                if item is None:
                    kind = "project_bullet" if right_id.startswith("project:") else "experience_bullet"
                    item = {
                        "id": right_id,
                        "kind": kind,
                        "original": right_text,
                        "source": right_text,
                        "complaints": [],
                    }
                    items.append(item)
                    item_map[right_id] = item
                item["complaints"].append("differentiate this from a near-duplicate bullet")

    if items:
        # The validator's human-readable output gives the model document-level
        # context without being used to locate edits.
        items[0]["validation_context"] = validation_issues
    return items


def repair_resume(
    resume: TailoredResume,
    profile: CandidateProfile,
    jd: JobDescription,
    validation_issues: list[str],
    model: str = _QUALITY_MODEL,
) -> TailoredResume:
    """Repair exact flagged items in one call; return the input on bad output."""
    items = _collect_items(resume, validation_issues)
    if not items:
        return resume

    system = (
        "You are a meticulous senior resume editor. Repair only the supplied items and address "
        "every complaint attached to each item. Return one result for every id.\n\n"
        "GROUNDING RULES:\n"
        "- Use only facts in original/source/project/technologies/existing_bullets.\n"
        "- Never introduce metrics, scale, outcomes, tools, ownership, or seniority not supplied.\n"
        "- Preserve every existing factual claim unless the complaint requires deleting vague filler.\n"
        "- A new_project_bullet must be distinct from existing bullets and must have direct source support.\n\n"
        "QUALITY RULES:\n"
        "- Open bullets with accurate, varied past-tense action verbs.\n"
        "- Vary evidence angles and sentence structures; avoid formulaic 'Built X using Y to Z' repetition.\n"
        "- Prefer precise technical nouns over decorative adjectives. Keep bullets concise and scannable.\n"
        "- Creativity is editorial framing, never factual invention.\n"
        "- Summaries use implied first person and no name or third-person pronouns.\n\n"
        "Return ONLY valid JSON: "
        '{"results": [{"id": str, "revised_text": str}]}'
    )
    payload = {
        "target_role": jd.role_title,
        "domain_signals": jd.domain_signals,
        "profile_source": profile.raw_text[:12000],
        "items": items,
    }
    response = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    try:
        data = json.loads(response.choices[0].message.content)
        revisions = {
            result["id"]: result["revised_text"].strip()
            for result in data.get("results", [])
            if isinstance(result, dict)
            and isinstance(result.get("id"), str)
            and isinstance(result.get("revised_text"), str)
            and result["revised_text"].strip()
        }
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
        return resume

    experiences = list(resume.experiences)
    projects = list(resume.projects)
    changes = list(resume.changes)
    summary = revisions.get("summary", resume.summary)

    for exp_index, exp in enumerate(experiences):
        bullets = list(exp.bullets)
        for bullet_index, bullet in enumerate(bullets):
            revised = revisions.get(f"experience:{exp_index}:{bullet_index}")
            if not revised or revised == bullet.text:
                continue
            change = BulletChange(
                original_text=bullet.text,
                revised_text=revised,
                change_reason="quality_repair",
                keywords_added=[],
            )
            bullets[bullet_index] = bullet.model_copy(update={"text": revised, "change": change})
            changes.append(change)
        experiences[exp_index] = exp.model_copy(update={"bullets": bullets})

    for project_index, project in enumerate(projects):
        bullets = list(project.bullets)
        for bullet_index, bullet in enumerate(list(bullets)):
            revised = revisions.get(f"project:{project_index}:{bullet_index}")
            if not revised or revised == bullet.text:
                continue
            bullets[bullet_index] = bullet.model_copy(update={"text": revised})
            changes.append(BulletChange(
                original_text=bullet.text,
                revised_text=revised,
                change_reason="quality_repair",
                keywords_added=[],
            ))
        for slot in range(len(bullets), 2):
            revised = revisions.get(f"project_new:{project_index}:{slot}")
            if not revised:
                continue
            source = project.source_text or project.description
            bullets.append(Bullet(text=revised, source_text=source))
            changes.append(BulletChange(
                original_text=source,
                revised_text=revised,
                change_reason="quality_repair",
                keywords_added=[],
            ))
        projects[project_index] = project.model_copy(update={"bullets": bullets})

    return resume.model_copy(update={
        "summary": summary,
        "experiences": experiences,
        "projects": projects,
        "changes": changes,
    })
