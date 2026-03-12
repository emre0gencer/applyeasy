"""
EvidenceExtractor — heuristic extraction of evidence signals from resume bullets.

No LLM calls. Fast and deterministic. Used by:
  - RelevanceRanker  (bullet contribution scoring)
  - ResumeTailoringEngine (evidence-constrained rewrite context)
  - QualityValidator  (evidence quality checks)
"""

from __future__ import annotations

import re

from backend.src.models.schemas import BulletEvidence

# ── Signal word lists ────────────────────────────────────────────────────────

_SCOPE_SIGNALS: list[str] = [
    "end-to-end",
    "full-stack",
    "fullstack",
    "user-facing",
    "production",
    "real-time",
    "realtime",
    "multi-entity",
    "cross-functional",
    "transactional",
    "multi-step",
    "distributed",
    "client-facing",
    "enterprise",
    "scalable",
    "high-volume",
    "mission-critical",
    "workflow-critical",
    "service-level",
    "system-wide",
    "large-scale",
]

_COMPLEXITY_SIGNALS: list[str] = [
    "schema design",
    "data model",
    "validation",
    "api integration",
    "state management",
    "experimentation",
    "evaluation pipeline",
    "evaluation",
    "debugging",
    "observability",
    "normalization",
    "asynchronous",
    "async",
    "concurrency",
    "rate limiting",
    "pagination",
    "authentication",
    "authorization",
    "caching",
    "indexing",
    "constraint",
    "edge case",
    "fault tolerance",
    "retry logic",
    "rollback",
    "migration",
    "multi-tenant",
    "role-based",
    "access control",
    "query optimization",
    "load balancing",
    "tracing",
    "monitoring",
    "logging",
    "test coverage",
    "integration test",
    "unit test",
]

_OWNERSHIP_VERBS: list[str] = [
    "designed",
    "built",
    "implemented",
    "evaluated",
    "integrated",
    "validated",
    "optimized",
    "refactored",
    "architected",
    "led",
    "owned",
    "developed",
    "created",
    "established",
    "launched",
    "delivered",
    "engineered",
    "constructed",
    "deployed",
    "automated",
    "migrated",
    "restructured",
    "diagnosed",
    "resolved",
    "orchestrated",
    "coordinated",
    "configured",
    "maintained",
    "extended",
]

# Space-padded to avoid partial-word matches (e.g. "app" inside "application")
_DELIVERABLE_SIGNALS: list[tuple[str, str]] = [
    (" api ", "api"),
    (" apis ", "api"),
    ("rest api", "rest api"),
    ("graphql api", "graphql api"),
    (" service ", "service"),
    (" endpoint", "endpoint"),
    (" database", "database"),
    (" schema", "schema"),
    (" pipeline", "pipeline"),
    (" dashboard", "dashboard"),
    (" workflow", "workflow"),
    (" application", "application"),
    (" system", "system"),
    (" module", "module"),
    (" component", "component"),
    (" interface", "interface"),
    (" platform", "platform"),
    (" backend", "backend"),
    (" frontend", "frontend"),
    (" microservice", "microservice"),
    ("batch job", "batch job"),
    ("cli tool", "cli tool"),
    (" library", "library"),
    (" sdk", "sdk"),
    ("query engine", "query engine"),
    ("data model", "data model"),
    ("test suite", "test suite"),
    ("ml workflow", "ml workflow"),
    ("evaluation pipeline", "evaluation pipeline"),
]


def extract_evidence(text: str) -> BulletEvidence:
    """
    Extract structured evidence signals from a resume bullet using keyword heuristics.

    Returns a BulletEvidence with:
      - scope_signals:        structural scope phrases detected
      - complexity_signals:   technical complexity phrases detected
      - ownership_signals:    strong ownership verbs detected
      - deliverable_signals:  concrete deliverable nouns detected
      - explicit_metrics:     literal numbers / percentages / multipliers
      - evidence_strength:    0.0–1.0 weighted composite of signal presence
      - quantifiable_info_score: 0.0–1.0 grounded information density
      - unsupported_claim_risk:  0.0–1.0 risk of vague inflation
    """
    # Pad with spaces for boundary-aware matching
    padded = " " + text.lower() + " "

    scope = [s for s in _SCOPE_SIGNALS if s in padded]
    complexity = [s for s in _COMPLEXITY_SIGNALS if s in padded]
    ownership = [v for v in _OWNERSHIP_VERBS if v in padded]
    deliverables = [label for (pattern, label) in _DELIVERABLE_SIGNALS if pattern in padded]
    # Remove deliverable duplicates while preserving order
    seen: set[str] = set()
    unique_deliverables: list[str] = []
    for d in deliverables:
        if d not in seen:
            unique_deliverables.append(d)
            seen.add(d)
    deliverables = unique_deliverables

    # Explicit metrics: numbers, percentages, multipliers, counts
    metrics = re.findall(r"\b\d+(?:[.,]\d+)?(?:\s*%|\s*x\b|\+)?\b", text)

    # ── Evidence strength ──────────────────────────────────────────────────
    # Metrics and complexity count most; ownership is a strong baseline signal;
    # scope and deliverables add structural depth
    ev = (
        min(len(metrics), 2) * 0.25
        + min(len(complexity), 3) * 0.25
        + min(len(ownership), 2) * 0.20
        + min(len(scope), 3) * 0.15
        + min(len(deliverables), 3) * 0.15
    )
    evidence_strength = round(min(ev, 1.0), 3)

    # ── Quantifiable information score ────────────────────────────────────
    # Rewards grounded specificity; penalizes pure length and keyword count
    qi = (
        min(len(metrics), 3) * 0.30
        + min(len(complexity), 2) * 0.30
        + min(len(scope), 2) * 0.20
        + min(len(deliverables), 2) * 0.10
        + min(len(ownership), 1) * 0.10
    )
    quantifiable_info_score = round(min(qi, 1.0), 3)

    # ── Unsupported claim risk ─────────────────────────────────────────────
    # A long bullet with only vague ownership verbs and no grounding signals
    # is more likely to contain inflated or poorly-supported claims
    word_count = len(text.split())
    if (
        word_count > 45
        and len(complexity) == 0
        and len(scope) == 0
        and len(metrics) == 0
        and len(deliverables) <= 1
    ):
        unsupported_risk = round(min(0.3 + (word_count - 45) * 0.01, 0.8), 3)
    else:
        unsupported_risk = 0.0

    action = ownership[0] if ownership else ""

    return BulletEvidence(
        action=action,
        scope_signals=scope,
        complexity_signals=complexity,
        ownership_signals=ownership,
        deliverable_signals=deliverables,
        explicit_metrics=metrics,
        evidence_strength=evidence_strength,
        quantifiable_info_score=quantifiable_info_score,
        unsupported_claim_risk=unsupported_risk,
    )
