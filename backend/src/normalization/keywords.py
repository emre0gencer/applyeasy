"""Canonicalize equivalent job-keyword spellings before scoring coverage."""

from __future__ import annotations

import re

from backend.src.models.schemas import KeywordEntry


_ALIASES = {
    "react": "React",
    "reactjs": "React",
    "node": "Node.js",
    "nodejs": "Node.js",
    "next": "Next.js",
    "nextjs": "Next.js",
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "amazonwebservices": "AWS",
    "aws": "AWS",
    "googlecloudplatform": "GCP",
    "gcp": "GCP",
    "csharp": "C#",
    "cplusplus": "C++",
    "dotnet": ".NET",
}


def _key(term: str) -> str:
    value = term.strip().lower().replace("&", "and")
    value = value.replace("c++", "cplusplus").replace("c#", "csharp")
    value = value.replace(".net", "dotnet")
    return re.sub(r"[^a-z0-9]+", "", value)


def canonical_keyword(term: str) -> str:
    """Return a stable display spelling while preserving unknown terms."""
    stripped = " ".join(term.split())
    return _ALIASES.get(_key(stripped), stripped)


def canonicalize_keywords(keywords: list[KeywordEntry]) -> list[KeywordEntry]:
    """Collapse aliases, retaining strongest importance and earliest provenance."""
    result: list[KeywordEntry] = []
    positions: dict[str, int] = {}
    for keyword in keywords:
        term = canonical_keyword(keyword.term)
        if not term:
            continue
        key = _key(term)
        if key not in positions:
            positions[key] = len(result)
            result.append(keyword.model_copy(update={"term": term}))
            continue
        index = positions[key]
        current = result[index]
        if keyword.importance > current.importance:
            result[index] = current.model_copy(update={"importance": keyword.importance})
    return result
