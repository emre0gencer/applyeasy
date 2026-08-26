"""Controlled vocabulary for skill categories.

`category` arrives as free text from the extraction model, so the Skills block
header vocabulary changes from run to run - "Languages" one time, "Programming
Languages" the next, "Technical Skills" the time after. Two resumes produced by
the same product should not disagree about what the sections are called.

Every extracted category is mapped onto a fixed set of canonical buckets, in a
fixed display order. When the model's label is unmappable the skill name itself
is checked against a lexicon, so "Bloomberg Terminal" lands in Tools & Platforms
even if the model filed it under something invented.
"""

from __future__ import annotations

from backend.src.models.schemas import Skill

# Display order is deliberate: what you write code in, what you build with,
# what you run it on, what you analyse with, then domain practice.
CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Languages",
    "Frameworks & Libraries",
    "Tools & Platforms",
    "Data & ML",
    "Domain",
    "Other",
)

_FALLBACK = "Other"

# Substring match against the model's own label, checked in order. First hit wins,
# so more specific phrases must precede the generic ones they contain.
_LABEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("programming language", "Languages"),
    ("language", "Languages"),          # after "programming language"
    ("framework", "Frameworks & Libraries"),
    ("librar", "Frameworks & Libraries"),
    ("web technolog", "Frameworks & Libraries"),
    ("frontend", "Frameworks & Libraries"),
    ("front-end", "Frameworks & Libraries"),
    ("backend", "Frameworks & Libraries"),
    ("back-end", "Frameworks & Libraries"),
    ("machine learning", "Data & ML"),
    ("deep learning", "Data & ML"),
    ("data scien", "Data & ML"),
    ("data analy", "Data & ML"),
    ("analytics", "Data & ML"),
    ("statistic", "Data & ML"),
    ("database", "Data & ML"),
    ("data", "Data & ML"),              # after the specific data* phrases
    ("devops", "Tools & Platforms"),
    ("cloud", "Tools & Platforms"),
    ("infrastructure", "Tools & Platforms"),
    ("platform", "Tools & Platforms"),
    ("tool", "Tools & Platforms"),
    ("technolog", "Tools & Platforms"),
    ("software", "Tools & Platforms"),
    ("finance", "Domain"),
    ("financial", "Domain"),
    ("valuation", "Domain"),
    ("product", "Domain"),
    ("business", "Domain"),
    ("methodolog", "Domain"),
    ("domain", "Domain"),
    ("certification", "Domain"),
)

# Checked against the skill name when the label is unmappable.
_SKILL_LEXICON: dict[str, str] = {
    # Languages
    "python": "Languages", "java": "Languages", "javascript": "Languages",
    "typescript": "Languages", "c": "Languages", "c++": "Languages",
    "c#": "Languages", "go": "Languages", "golang": "Languages",
    "rust": "Languages", "ruby": "Languages", "php": "Languages",
    "swift": "Languages", "kotlin": "Languages", "scala": "Languages",
    "r": "Languages", "matlab": "Languages", "sql": "Languages",
    "bash": "Languages", "shell": "Languages", "html": "Languages",
    "css": "Languages", "vba": "Languages",
    # Frameworks & Libraries
    "react": "Frameworks & Libraries", "react.js": "Frameworks & Libraries",
    "vue": "Frameworks & Libraries", "angular": "Frameworks & Libraries",
    "node.js": "Frameworks & Libraries", "node": "Frameworks & Libraries",
    "express": "Frameworks & Libraries", "django": "Frameworks & Libraries",
    "flask": "Frameworks & Libraries", "fastapi": "Frameworks & Libraries",
    "spring": "Frameworks & Libraries", "rails": "Frameworks & Libraries",
    "next.js": "Frameworks & Libraries", "sqlalchemy": "Frameworks & Libraries",
    "celery": "Frameworks & Libraries", "jquery": "Frameworks & Libraries",
    # Tools & Platforms
    "git": "Tools & Platforms", "github": "Tools & Platforms",
    "gitlab": "Tools & Platforms", "docker": "Tools & Platforms",
    "kubernetes": "Tools & Platforms", "aws": "Tools & Platforms",
    "gcp": "Tools & Platforms", "azure": "Tools & Platforms",
    "linux": "Tools & Platforms", "jenkins": "Tools & Platforms",
    "terraform": "Tools & Platforms", "jira": "Tools & Platforms",
    "figma": "Tools & Platforms", "excel": "Tools & Platforms",
    "powerpoint": "Tools & Platforms", "bloomberg terminal": "Tools & Platforms",
    "bloomberg": "Tools & Platforms", "capiq": "Tools & Platforms",
    "pitchbook": "Tools & Platforms", "tableau": "Tools & Platforms",
    "rabbitmq": "Tools & Platforms", "redis": "Tools & Platforms",
    "github actions": "Tools & Platforms", "ci/cd": "Tools & Platforms",
    "amplitude": "Tools & Platforms", "mixpanel": "Tools & Platforms",
    # Data & ML
    "pandas": "Data & ML", "numpy": "Data & ML", "scikit-learn": "Data & ML",
    "sklearn": "Data & ML", "pytorch": "Data & ML", "tensorflow": "Data & ML",
    "keras": "Data & ML", "postgresql": "Data & ML", "postgres": "Data & ML",
    "mysql": "Data & ML", "mongodb": "Data & ML", "spark": "Data & ML",
    "hadoop": "Data & ML", "airflow": "Data & ML", "dbt": "Data & ML",
    "snowflake": "Data & ML", "bigquery": "Data & ML",
    # Domain
    "dcf": "Domain", "lbo": "Domain", "financial modeling": "Domain",
    "valuation": "Domain", "a/b testing": "Domain", "agile": "Domain",
    "scrum": "Domain", "product roadmapping": "Domain",
    "user research": "Domain",
}


def canonical_category(label: str | None, skill_name: str = "") -> str:
    """Map a free-text category label onto the canonical vocabulary.

    Falls back to the skill name's own lexicon entry, then to "Other".
    """
    if label:
        lowered = label.strip().lower()
        for needle, canonical in _LABEL_ALIASES:
            if needle in lowered:
                return canonical

    name_key = skill_name.strip().lower()
    if name_key in _SKILL_LEXICON:
        return _SKILL_LEXICON[name_key]

    return _FALLBACK


def normalize_skills(skills: list[Skill]) -> list[Skill]:
    """Reassign every skill to a canonical category and drop duplicate names.

    Duplicates are matched case-insensitively; the first occurrence wins, so the
    originally extracted casing (which came from the candidate's own text) is
    what survives.
    """
    if not skills:
        return skills

    seen: set[str] = set()
    normalized: list[Skill] = []
    for skill in skills:
        key = skill.name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(
            skill.model_copy(
                update={"category": canonical_category(skill.category, skill.name)}
            )
        )
    return normalized


def order_skill_groups(grouped: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return the grouped skills in canonical display order.

    Any category outside the vocabulary (there should be none after
    `normalize_skills`, but the renderer is defensive) is appended at the end in
    its incoming order.
    """
    ordered: dict[str, list[str]] = {}
    for category in CANONICAL_CATEGORIES:
        if grouped.get(category):
            ordered[category] = grouped[category]
    for category, names in grouped.items():
        if category not in ordered and names:
            ordered[category] = names
    return ordered
