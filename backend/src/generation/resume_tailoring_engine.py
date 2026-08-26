"""
ResumeTailoringEngine — selection + reorder + constrained LLM rephrasing.

Selection logic is deterministic. LLM calls are batched to minimize API cost:
  - Experience bullets rephrased in one QUALITY call, which ALSO returns the
    2-sentence summary (folded in; standalone summary call is a fallback only).
  - All project bullets rephrased in one FAST call (across every eligible project).
  - Page-fill bullets generated in one FAST call (across every under-filled project).
  - Skills classification is deterministic (embedding nearest-category) — no LLM.
"""

from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
from groq import Groq

from backend.src.analysis.evidence_extractor import extract_evidence
from backend.src.matching.relevance_ranker import _cosine_sim, _embed
from backend.src.models.schemas import (
    Bullet,
    BulletChange,
    BulletEvidence,
    CandidateProfile,
    EducationEntry,
    ExperienceEntry,
    ExperienceRelevanceMap,
    JobDescription,
    KeywordEntry,
    ProjectEntry,
    ScoredBullet,
    ScoredEntry,
    Skill,
    TailoredBullet,
    TailoredExperience,
    TailoredResume,
)
from backend.src.normalization.ordering import (
    normalize_education,
    normalize_experiences,
    normalize_projects,
)
from backend.src.normalization.skills import normalize_skills

_client: "Groq | None" = None

_FAST_MODEL = "llama-3.1-8b-instant"
_QUALITY_MODEL = "llama-3.3-70b-versatile"


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"), timeout=30.0, max_retries=2)
    return _client


# Limits
_MAX_EXPERIENCES = 3       # cap included experience entries
_MIN_EXPERIENCES = 2       # always include at least this many, even if low relevance
_MAX_BULLETS_PER_EXP = 3  # bullets per experience
_MAX_KEYWORD_INTEGRATIONS = 5  # per resume total
_ENTRY_THRESHOLD = 0.15   # minimum relevance score to include an entry
_PROJECT_TAILOR_THRESHOLD = 0.28  # minimum project score to attempt keyword integration

# Page budget (calibrated for classic compressed template at 9pt)
# ~3600 chars fits on one letter page at 0.38in/0.33in margins
_PAGE_CAPACITY_CHARS = 3600
_PAGE_FILL_HARD_LIMIT = 0.93  # never exceed 93% — guarantees one page
_PAGE_FILL_SOFT_TARGET = 0.80  # aim for at least 80%; trigger fill pass below this


def _get_high_importance_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords if k.importance >= 2]


def _get_all_keywords(jd: JobDescription) -> list[str]:
    return [k.term for k in jd.keywords]


def _assign_keywords_to_bullets(
    keywords: list[str],
    bullets: list[tuple[int, int, str]],  # (exp_i, b_i, text)
) -> dict[tuple[int, int], list[str]]:
    """
    Globally assign each keyword to the single best-matching bullet across ALL entries.

    Each keyword is used exactly once. For each keyword, the best bullet is chosen
    by word-overlap score between the keyword tokens and bullet text — so keywords
    land where they are most contextually relevant, not just in sequential order.

    Keywords already present verbatim in a bullet are skipped for that bullet
    (no point re-adding what's already there); the next-best bullet is tried instead.

    Returns a dict mapping (exp_i, b_i) → list of keywords assigned to that bullet.
    """
    assignments: dict[tuple[int, int], list[str]] = {(ei, bi): [] for ei, bi, _ in bullets}
    used_keywords: set[str] = set()

    # Pre-tokenize bullet texts for scoring
    bullet_words: list[set[str]] = [
        set(text.lower().split()) for _, _, text in bullets
    ]
    bullet_texts_lower: list[str] = [text.lower() for _, _, text in bullets]

    for kw in keywords:
        if kw.lower() in used_keywords:
            continue

        kw_tokens = set(kw.lower().split())

        # Score each bullet: word overlap, penalise bullets that already contain this keyword
        best_score = -1.0
        best_idx = -1
        for bi, (bwords, btext_lower) in enumerate(zip(bullet_words, bullet_texts_lower)):
            if kw.lower() in btext_lower:
                continue  # already present — skip
            if not bwords:
                continue
            overlap = len(kw_tokens & bwords) / len(bwords)
            if overlap > best_score:
                best_score = overlap
                best_idx = bi

        # If every bullet already contains the keyword, skip it entirely
        if best_idx == -1:
            continue

        key = (bullets[best_idx][0], bullets[best_idx][1])
        assignments[key].append(kw)
        used_keywords.add(kw.lower())

    return assignments


def _rephrase_bullets_batch(
    bullets: list[tuple[str, list[str], "BulletEvidence | None"]],
    role_title: str,
    domain_signals: "list[str] | None" = None,
    evidence_style: str = "",
    summary_context: "dict | None" = None,
    model: str = _QUALITY_MODEL,
) -> tuple[list[tuple[str, list[str]]], str]:
    """
    Single Groq call to rewrite ALL bullets using evidence-grounded, recruiter-useful prompting.

    bullets = list of (original_text, keywords_to_try, evidence_signals_or_None)
    Returns (list of (revised_text, keywords_added), summary).

    When summary_context is provided, the same QUALITY call also writes the
    2-sentence resume summary (folded in to save a separate QUALITY call); the
    summary is "" otherwise or if the model omits it.

    v2 change: The primary rewrite objective is to surface concrete evidence —
    scope, complexity, ownership, and deliverable specificity.
    Keywords are secondary: integrated only where they fit the evidence naturally.
    """
    if not bullets:
        return [], ""

    domain_context = ""
    if domain_signals:
        domain_context = f"\nRole domain focus: {', '.join(domain_signals[:3])}"
    if evidence_style:
        domain_context += f"\nEvidence this role values: {evidence_style}"

    system = (
        "You are a senior technical resume writer. Your goal is to make each bullet "
        "more informative, more specific, and more useful to a recruiter — "
        "by surfacing real evidence of what was done, how it was done, and what it produced.\n\n"

        "PRIMARY OBJECTIVE — KEYWORD INTEGRATION:\n"
        "You MUST weave the provided keywords_to_try into each bullet naturally. "
        "Every keyword given must appear verbatim in the revised bullet. "
        "Restructure the sentence as needed to include them while keeping the bullet coherent and professional.\n\n"

        "SECONDARY OBJECTIVE — EVIDENCE:\n"
        "While integrating keywords, also surface concrete evidence:\n"
        "  - Scope: end-to-end, user-facing, production-ready, multi-step, workflow-critical\n"
        "  - Complexity: schema design, validation logic, API integration, state management\n"
        "  - Ownership: designed, built, implemented, validated, optimized, deployed\n"
        "  - Deliverable: named system/API/pipeline/schema/workflow/layer\n\n"

        "KEYWORD INTEGRATION RULES:\n"
        "  - Include every keyword from keywords_to_try verbatim in the revised_text.\n"
        "  - List every included keyword in keywords_added exactly as given.\n"
        "  - Fit keywords naturally into the sentence — rephrase around them if needed.\n"
        "  - Never drop a keyword just because it requires rephrasing.\n\n"

        "FORMULA: ownership verb + technical method/approach + scope/context + deliverable/outcome\n\n"

        "STYLE RULES:\n"
        "1. 35-55 words per bullet. Complete sentences — not fragments.\n"
        "2. Open with a strong past-tense action verb (Designed, Built, Implemented, Engineered, "
        "Optimized, Deployed, Refactored, Integrated, Evaluated, Automated, Architected, Migrated).\n"
        "3. Name technologies, frameworks, and patterns explicitly — never say 'a tool' or 'a library'.\n"
        "4. Vary action verbs — do not reuse the same verb across bullets in the same entry.\n"
        "5. No first-person pronouns. No filler adjectives (passionate, innovative, dynamic).\n"
        "6. Prefer denser, more informative bullets over longer keyword-heavy ones.\n"
        "7. Each bullet must be independently meaningful to a hiring manager scanning the resume.\n\n"

        "CREATIVE RANGE — vary the evidence angle and sentence architecture without changing facts:\n"
        "  - architecture/design, implementation method, reliability/quality, integration/delivery, "
        "or user/business value (only when the source states it)\n"
        "  - avoid repeating the template 'Built X using Y to Z' across the batch\n"
        "  - use precise technical nouns and specific transitions instead of decorative adjectives\n\n"

        "ABSOLUTE PROHIBITIONS — Never invent:\n"
        "  - Percentages, counts, team sizes, latency numbers, revenue figures\n"
        "  - Tools, technologies, frameworks, or libraries not in the original bullet\n"
        "  - Scope claims ('large-scale', 'millions of') not grounded in the original\n"
        "  - Ownership levels ('led a team of 5') not stated in the original\n"
        "  - Outcomes or results not mentioned in the original\n"
        "  - Seniority indicators (led, managed) not present in the original\n\n"
    )

    if summary_context:
        system += (
            "ALSO WRITE A 2-SENTENCE RESUME SUMMARY for this candidate targeting the role:\n"
            "  Sentence 1: experience depth, key technical background, and most relevant skills; "
            "weave in 2-3 target keywords naturally.\n"
            "  Sentence 2: one concrete technical differentiator aligned with what the role's domain values.\n"
            "  VOICE — the rule most often broken:\n"
            "    - Write in implied first person, opening with the professional descriptor, e.g.\n"
            "      'Backend engineer with three years building payment infrastructure...'\n"
            "    - NEVER write the candidate's name in the summary.\n"
            "    - NEVER use he, she, they, or any third-person pronoun.\n"
            "    - NEVER use I, my, or me either — the subject stays implied.\n"
            "  - Only reference provided profile elements; do NOT fabricate achievements, metrics, or skills.\n"
            "  - No generic phrases (passionate, results-driven, team player, proven track record, eager to).\n"
            "  - Maximum 85 words, exactly 2 sentences.\n\n"
            "Return ONLY valid JSON: "
            '{"results": [{"revised_text": str, "keywords_added": [str]}], "summary": str}'
            " — one result per input bullet in the same order."
        )
    else:
        system += (
            "Return ONLY valid JSON: "
            '{"results": [{"revised_text": str, "keywords_added": [str]}]}'
            " — one result per input bullet in the same order."
        )

    items = []
    for i, (text, kws, ev) in enumerate(bullets):
        item: dict = {
            "index": i,
            "original": text,
            "keywords_to_try": kws,
            "target_role": role_title,
        }
        if ev:
            item["evidence_signals"] = {
                "scope": ev.scope_signals[:3],
                "complexity": ev.complexity_signals[:3],
                "ownership": ev.ownership_signals[:2],
                "deliverables": ev.deliverable_signals[:2],
                "metrics": ev.explicit_metrics[:2],
            }
        items.append(item)

    user_msg = f"Target role: {role_title}{domain_context}\nBullets to rewrite:\n{json.dumps(items)}"
    if summary_context:
        user_msg += (
            "\n\nSUMMARY CONTEXT —"
            f" Recent roles: {summary_context.get('exp_titles', '')};"
            f" Skills: {summary_context.get('skills', '')};"
            f" Target role: {summary_context.get('target_role', '')};"
            f" Target keywords: {summary_context.get('keywords', '')};"
            f" Seniority: {summary_context.get('seniority', '')}"
            f"{summary_context.get('domain', '')}"
        )

    resp = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        results = data.get("results", [])
        parsed = [
            (r.get("revised_text", bullets[i][0]), r.get("keywords_added", []))
            for i, r in enumerate(results)
            if i < len(bullets)
        ]
        summary = (data.get("summary") or "").strip()
        return parsed, summary
    except (json.JSONDecodeError, AttributeError, IndexError):
        return [(text, []) for text, _, _ev in bullets], ""


def _rephrase_project_bullets_batch(
    items: list[tuple[str, str, list[str]]],  # (project_name, original_text, keywords_to_try)
    model: str = _FAST_MODEL,
) -> list[tuple[str, list[str]]]:
    """
    Single Groq call to rephrase project bullets across ALL eligible projects.

    Each item carries its own project name, so the model gets exactly the same
    per-bullet context it had when this ran as one call per project — but in a
    single batched request (N projects → 1 call). Returns (revised_text,
    keywords_added) aligned 1:1 with the input order.

    v2: Primary objective shifted from keyword integration to evidence surfacing.
    """
    if not items:
        return []

    system = (
        "You are a senior technical resume writer. Improve each project bullet to surface "
        "concrete evidence of what was built, how it worked, and what it delivered — "
        "while preserving the original scope and technical stack entirely.\n\n"
        "PRIMARY OBJECTIVE — KEYWORD INTEGRATION:\n"
        "You MUST include every keyword from keywords_to_try verbatim in the revised bullet. "
        "Rephrase the sentence as needed to fit them naturally. "
        "List every included keyword in keywords_added exactly as given.\n\n"
        "SECONDARY OBJECTIVE — EVIDENCE:\n"
        "  - Name the deliverable: system, API, pipeline, schema, workflow, application\n"
        "  - Surface what was technically interesting: validation, schema design, API integration\n"
        "  - Clarify ownership: designed, built, implemented, integrated, evaluated\n\n"
        "RULES:\n"
        "1. Do NOT invent tools, technologies, metrics, outcomes, or scope not in the original.\n"
        "2. Keep length close to the original (25-45 words). Do not bloat.\n"
        "3. Open with a strong past-tense action verb.\n"
        "4. Preserve the original technical stack and outcomes exactly.\n"
        "5. Prefer a denser, more informative bullet over a longer keyword-heavy one.\n"
        "6. Each bullet belongs to the project named in its 'project' field — use that for context only.\n"
        "7. Give each bullet a distinct evidence angle (architecture, implementation, integration, "
        "quality/reliability, or grounded user value) and vary sentence structure across the batch.\n"
        "8. Avoid formulaic repetition such as opening every bullet with 'Built' or repeatedly using "
        "the pattern 'X using Y to Z'. Creativity means sharper framing of supplied evidence, not new facts.\n"
        "Return ONLY valid JSON: "
        '{"results": [{"revised_text": str, "keywords_added": [str]}]}'
        " — one result per input bullet in the same order."
    )
    payload = [
        {"index": i, "original": text, "keywords_to_try": kws, "project": project_name}
        for i, (project_name, text, kws) in enumerate(items)
    ]
    user_msg = (
        "Rephrase each project bullet below. Each carries its project name for context.\n"
        f"Bullets:\n{json.dumps(payload)}"
    )

    resp = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        results = data.get("results", [])
        return [
            (r.get("revised_text", items[i][1]), r.get("keywords_added", []))
            for i, r in enumerate(results)
            if i < len(items)
        ]
    except (json.JSONDecodeError, AttributeError, IndexError):
        return [(text, []) for _pname, text, _kws in items]


def _generate_summary(
    profile: CandidateProfile,
    jd: JobDescription,
    selected_experiences: list[TailoredExperience],
    model: str = _QUALITY_MODEL,
) -> str:
    """Generate a resume summary using llama-3.3-70b-versatile.

    v2: Uses domain_signals and evidence_style from the JD to make the
    summary reflect what the role actually values, not just keyword coverage.
    """
    exp_titles = ", ".join(e.role_title for e in selected_experiences[:3])
    skills_snippet = ", ".join(s.name for s in profile.skills[:10])
    top_kw = ", ".join(_get_high_importance_keywords(jd)[:6])
    domain_context = ""
    if jd.domain_signals:
        domain_context = f"\nRole domain signals: {', '.join(jd.domain_signals[:3])}"
    if jd.evidence_style:
        domain_context += f"\nEvidence this role values: {jd.evidence_style}"

    system = (
        "Write a 2-sentence resume summary for the given candidate targeting the given role.\n"
        "STRUCTURE:\n"
        "  Sentence 1: The candidate's experience depth, key technical background, and most relevant "
        "skills for this specific role. Incorporate 2-3 target keywords naturally.\n"
        "  Sentence 2: State the specific technical value the candidate brings — one concrete "
        "differentiator that aligns with what the role domain values most "
        "(reference the role's domain signals and evidence style when relevant).\n"
        "VOICE:\n"
        "  - Write in implied first person, opening with the professional descriptor "
        "(e.g. 'Backend engineer with three years building payment infrastructure...').\n"
        "  - NEVER write the candidate's name in the summary.\n"
        "  - NEVER use he, she, they, or any third-person pronoun.\n"
        "  - NEVER use I, my, or me either — the subject stays implied.\n"
        "RULES:\n"
        "1. Only reference background elements present in the provided profile data.\n"
        "2. Do NOT fabricate achievements, metrics, or skills not listed.\n"
        "3. No generic phrases: 'passionate', 'results-driven', 'team player', 'fast learner', "
        "'proven track record', 'excited to', 'eager to'.\n"
        "4. Maximum 85 words total. Output only the 2 sentences — no labels, no extra text."
    )
    # The candidate's name is deliberately withheld — supplying it is what
    # produced "Alex Rivera has experience as a Software Engineer..." in every
    # shipped sample. The summary never needs to name its subject.
    user_msg = (
        f"Recent roles: {exp_titles}\n"
        f"Skills: {skills_snippet}\n"
        f"Target role: {jd.role_title} at {jd.company_name or 'the company'}\n"
        f"Target keywords: {top_kw}\n"
        f"Seniority: {jd.seniority_level}"
        f"{domain_context}"
    )

    resp = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
    )
    return resp.choices[0].message.content.strip()


def _select_and_tailor_experiences(
    profile: CandidateProfile,
    relevance_map: ExperienceRelevanceMap,
    jd: JobDescription,
    keyword_integration_budget: list[int],  # mutable counter [remaining]
    keyword_limit: int = 10,
    model: str = _QUALITY_MODEL,
) -> tuple[list[TailoredExperience], str]:
    """Select top experiences and tailor their bullets using a single batch LLM call.

    The same QUALITY batch call also returns the resume summary (folded in to
    avoid a separate QUALITY call); returns (experiences, summary). The summary
    may be "" if there were no bullets to rephrase or the model omitted it — the
    caller falls back to a standalone summary generation in that case.
    """
    all_exp_entries = [e for e in relevance_map.scored_entries if e.entry_type == "experience"]
    above_threshold = [e for e in all_exp_entries if e.overall_score >= _ENTRY_THRESHOLD]
    below_threshold = [e for e in all_exp_entries if e.overall_score < _ENTRY_THRESHOLD]

    # Always include research/researcher entries if present — keep top scored others
    def _is_research(idx: int) -> bool:
        if idx >= len(profile.experiences):
            return False
        return any(kw in profile.experiences[idx].role_title.lower()
                   for kw in ("research", "researcher"))

    research = [e for e in above_threshold if _is_research(e.entry_index)]
    non_research = [e for e in above_threshold if not _is_research(e.entry_index)]
    slots_left = _MAX_EXPERIENCES - len(research)
    exp_entries = (research + non_research[:max(slots_left, 0)])[:_MAX_EXPERIENCES]

    # Guarantee at least _MIN_EXPERIENCES — pad with best below-threshold entries if needed
    if len(exp_entries) < _MIN_EXPERIENCES:
        below_sorted = sorted(below_threshold, key=lambda e: e.overall_score, reverse=True)
        needed = _MIN_EXPERIENCES - len(exp_entries)
        exp_entries = exp_entries + below_sorted[:needed]

    # Track which are padded so we don't keyword-inject into low-relevance entries
    padded_set: set[int] = set(range(
        min(_MAX_EXPERIENCES, max(len(research) + max(slots_left, 0), 0)),
        len(exp_entries),
    ))

    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    role_title = jd.role_title

    # Pass 1: collect sorted bullets per entry
    per_exp_sorted: list[list[ScoredBullet]] = []
    for exp_i, scored_entry in enumerate(exp_entries):
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            per_exp_sorted.append([])
            continue
        sorted_bullets = sorted(
            scored_entry.scored_bullets,
            key=lambda sb: sb.bullet_contribution_score,
            reverse=True,
        )[:_MAX_BULLETS_PER_EXP]
        per_exp_sorted.append(sorted_bullets)

    # Pass 2: global keyword assignment — each keyword goes to its best-matching bullet
    # Only non-padded entries are eligible for keyword injection
    candidate_kws = list(dict.fromkeys(high_kw + all_kw))[:keyword_limit]
    eligible_bullets: list[tuple[int, int, str]] = []  # (exp_i, b_i, text)
    for exp_i, sorted_bullets in enumerate(per_exp_sorted):
        if exp_i in padded_set:
            continue
        for b_i, sb in enumerate(sorted_bullets):
            eligible_bullets.append((exp_i, b_i, sb.bullet.text))

    global_kw_assignments = _assign_keywords_to_bullets(candidate_kws, eligible_bullets)

    # Pass 3: build rephrase queue using global assignments
    rephrase_queue: list[tuple[int, int, str, list[str], "BulletEvidence | None"]] = []
    for exp_i, sorted_bullets in enumerate(per_exp_sorted):
        if exp_i in padded_set:
            continue
        for b_i, sb in enumerate(sorted_bullets):
            assigned_kws = global_kw_assignments.get((exp_i, b_i), [])
            evidence = sb.evidence if sb.evidence is not None else extract_evidence(sb.bullet.text)
            rephrase_queue.append((exp_i, b_i, sb.bullet.text, assigned_kws, evidence))

    # Build summary context so the batched QUALITY call can also write the summary
    # (Opt 5: folds the standalone summary call into this one).
    selected_titles = [
        profile.experiences[e.entry_index].role_title
        for e in exp_entries
        if e.entry_index < len(profile.experiences)
    ]
    summary_domain = ""
    if jd.domain_signals:
        summary_domain = f"; Role domain signals: {', '.join(jd.domain_signals[:3])}"
    if jd.evidence_style:
        summary_domain += f"; Evidence this role values: {jd.evidence_style}"
    # No "name" key — see _generate_summary. A summary that names its own
    # subject reads as a third-party write-up, not a resume.
    summary_context = {
        "exp_titles": ", ".join(selected_titles[:3]),
        "skills": ", ".join(s.name for s in profile.skills[:10]),
        "target_role": f"{jd.role_title} at {jd.company_name or 'the company'}",
        "keywords": ", ".join(_get_high_importance_keywords(jd)[:6]),
        "seniority": jd.seniority_level,
        "domain": summary_domain,
    }

    # Single batch call for all bullets needing rephrasing — also returns the summary.
    # v2: pass evidence context and JD domain signals to the evidence-constrained rewriter
    batch_inputs = [(text, kws, ev) for _, _, text, kws, ev in rephrase_queue]
    if batch_inputs:
        batch_results, summary = _rephrase_bullets_batch(
            batch_inputs, role_title,
            domain_signals=jd.domain_signals,
            evidence_style=jd.evidence_style,
            summary_context=summary_context,
            model=model,
        )
    else:
        batch_results, summary = [], ""

    # Map results back: (exp_i, b_i) → (revised_text, keywords_added)
    rephrase_map: dict[tuple[int, int], tuple[str, list[str]]] = {}
    for qi, (exp_i, b_i, _original_text, _, _ev) in enumerate(rephrase_queue):
        if qi < len(batch_results):
            revised, kws_added = batch_results[qi]
            rephrase_map[(exp_i, b_i)] = (revised, kws_added)

    # Assemble TailoredExperience objects
    tailored_experiences: list[TailoredExperience] = []
    for exp_i, scored_entry in enumerate(exp_entries):
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            continue
        exp = profile.experiences[idx]
        sorted_bullets = per_exp_sorted[exp_i]

        tailored_bullets: list[TailoredBullet] = []
        for b_i, sb in enumerate(sorted_bullets):
            original_text = sb.bullet.text
            if (exp_i, b_i) in rephrase_map:
                revised_text, keywords_added = rephrase_map[(exp_i, b_i)]
                change_reason = "keyword_integration" if revised_text != original_text else "unchanged"
            else:
                revised_text = original_text
                keywords_added = []
                change_reason = "unchanged"

            tailored_bullets.append(TailoredBullet(
                text=revised_text,
                source_text=sb.bullet.source_text,
                change=BulletChange(
                    original_text=original_text,
                    revised_text=revised_text,
                    change_reason=change_reason,
                    keywords_added=keywords_added,
                ),
                relevance_score=sb.relevance_score,
            ))

        tailored_experiences.append(TailoredExperience(
            company=exp.company,
            role_title=exp.role_title,
            start_date=exp.start_date,
            end_date=exp.end_date,
            location=exp.location,
            bullets=tailored_bullets,
        ))

    return tailored_experiences, summary


def _estimate_chars(
    summary: str,
    experiences: list[TailoredExperience],
    education: list[EducationEntry],
    skills: list[Skill],
    projects: list[ProjectEntry],
    leadership_items: list[str],
    awards: list[AwardEntry],
) -> int:
    """Character count estimate used for one-page budget decisions."""
    parts: list[str] = [summary]
    for exp in experiences:
        parts += [exp.role_title, exp.company]
        parts += [tb.text for tb in exp.bullets]
    for edu in education:
        parts += [edu.institution, edu.degree or ""]
        if edu.coursework:
            parts.append(edu.coursework)
    for s in skills:
        parts.append(s.name)
    for proj in projects:
        parts.append(proj.name)
        if proj.bullets:
            parts += [b.text for b in proj.bullets[:3]]
        elif proj.description:
            parts.append(proj.description)
    for item in leadership_items:
        parts.append(item)
    for award in awards:
        parts.append(award.title)
    return sum(len(p) for p in parts if p)


def _project_chars(proj: ProjectEntry) -> int:
    """Estimate chars a single project entry would add."""
    parts = [proj.name]
    if proj.bullets:
        parts += [b.text for b in proj.bullets[:3]]
    elif proj.description:
        parts.append(proj.description)
    return sum(len(p) for p in parts if p)


def _rank_project_candidates(
    profile: CandidateProfile,
    relevance_map: ExperienceRelevanceMap,
) -> list[tuple[ProjectEntry, float]]:
    """Return projects in relevance order while preserving stable ties."""
    scores = {
        entry.entry_index: entry.overall_score
        for entry in relevance_map.scored_entries
        if entry.entry_type == "project"
    }
    indexed = [
        (project, scores.get(index, 0.0), index)
        for index, project in enumerate(profile.projects)
    ]
    indexed.sort(key=lambda item: (-item[1], item[2]))
    return [(project, score) for project, score, _index in indexed]


def _generate_extra_project_bullets_batch(
    requests: list[tuple[int, ProjectEntry, int]],  # (proj_index, project, n_new)
    jd: JobDescription,
    model: str = _FAST_MODEL,
) -> dict[int, list[Bullet]]:
    """
    Generate extra grounded bullets for several under-filled projects in ONE call
    (was one FAST call per project). Each bullet is grounded exclusively in its
    project's source_text/description/technologies/existing bullets — never invents
    new facts. Returns {proj_index: [Bullet, ...]} capped at the requested n_new.
    """
    requests = [(pi, p, n) for pi, p, n in requests if n > 0]
    if not requests:
        return {}

    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    target_kws = list(dict.fromkeys(high_kw + all_kw))[:4]

    system = (
        "You are a senior technical resume writer. For each project below, generate additional "
        "resume bullet points grounded ONLY in the information explicitly provided for THAT project "
        "(source description, technologies, existing bullets). "
        "Do NOT invent new tools, metrics, outcomes, or any claim not already implied.\n\n"
        "RULES:\n"
        "1. Each new bullet must cover a distinct aspect not already in that project's existing bullets.\n"
        "2. 30-50 words per bullet. Open with a strong past-tense action verb.\n"
        "3. Integrate the provided target keywords only where they fit naturally.\n"
        "4. Never duplicate or restate an existing bullet.\n"
        "5. Generate exactly the requested count per project; if you cannot produce a grounded, "
        "distinct bullet, return fewer for that project.\n"
        "6. Keep each project's bullets under its own 'index'.\n"
        "7. Deliberately vary evidence angles across a project's bullets: architecture/design, "
        "implementation method, integration, reliability/quality, and grounded user value.\n"
        "8. Vary action verbs and sentence structures. Avoid repeatedly using 'Built' and avoid "
        "recycling the formula 'X using Y to Z'.\n"
        "9. Creativity is editorial: find a sharper way to frame the supplied evidence. It never "
        "licenses a new fact, implied outcome, technology, metric, scale, or ownership claim.\n"
        "Return ONLY valid JSON: "
        '{"projects": [{"index": int, "bullets": ["bullet text", ...]}]}'
    )

    payload = [
        {
            "index": pi,
            "project": proj.name,
            "technologies": proj.technologies[:6],
            "source_description": (proj.source_text or proj.description or "")[:600],
            "existing_bullets": [b.text for b in proj.bullets],
            "n_new": n_new,
        }
        for pi, proj, n_new in requests
    ]
    user_msg = (
        f"Target role: {jd.role_title}\n"
        f"Target keywords to try: {target_kws}\n"
        f"Projects:\n{json.dumps(payload)}"
    )

    resp = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    n_by_index = {pi: n for pi, _p, n in requests}
    source_by_index = {
        pi: (project.source_text or project.description)
        for pi, project, _n in requests
    }
    out: dict[int, list[Bullet]] = {}
    try:
        data = json.loads(resp.choices[0].message.content)
        for entry in data.get("projects", []):
            pi = entry.get("index")
            if pi not in n_by_index:
                continue
            raw = entry.get("bullets", []) or []
            bullets = [
                Bullet(text=b.strip(), source_text=source_by_index.get(pi, ""))
                for b in raw[:n_by_index[pi]]
                if isinstance(b, str) and b.strip()
            ]
            if bullets:
                out[pi] = bullets
        return out
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {}


# Soft-skill / generic terms that should never enter the skills section.
_SOFT_SKILL_STOPWORDS = {
    "communication", "teamwork", "team work", "collaboration", "leadership",
    "problem solving", "problem-solving", "time management", "adaptability",
    "creativity", "critical thinking", "interpersonal", "organization",
    "detail oriented", "detail-oriented", "self motivated", "self-motivated",
    "work ethic", "fast learner", "team player", "passion", "passionate",
    "motivated", "flexible", "responsibility", "initiative", "willingness",
    "enthusiasm", "multitasking", "attention to detail", "results driven",
    "results-driven", "proactive", "hardworking", "hard working",
}

_CATEGORY_SIM_THRESHOLD = 0.25  # cosine floor to attach a keyword to a category


def _looks_like_skill(kw: str) -> bool:
    """Heuristic include/exclude filter (replaces the LLM's yes/no judgement)."""
    k = kw.strip().lower()
    if not k or len(k) > 40:
        return False
    if k in _SOFT_SKILL_STOPWORDS:
        return False
    # Genuine tools/languages/frameworks are short; long phrases are usually prose.
    if len(k.split()) > 3:
        return False
    return True


def _add_keywords_to_skills(
    keywords_added: list[str],
    existing_skills: list[Skill],
    jd: JobDescription,
) -> list[Skill]:
    """
    Classify newly integrated keywords into the resume's existing skill categories
    and return an augmented skills list. Only genuine technical skills/tools/
    technologies are included; soft-skill terms and generic concepts are skipped.
    Already-present skills are never duplicated.

    Opt 4: deterministic — no LLM call. Inclusion is decided by a stoplist/heuristic
    and each kept keyword is assigned to the nearest existing category by cosine
    similarity against that category's skill-name centroid (reusing the embedding
    model already loaded for relevance ranking).
    """
    if not keywords_added:
        return existing_skills

    existing_names_lower = {s.name.lower() for s in existing_skills}
    unique_new = list(dict.fromkeys(
        k for k in keywords_added
        if k.lower() not in existing_names_lower and _looks_like_skill(k)
    ))
    if not unique_new:
        return existing_skills

    # Group existing skills by category to build per-category centroids.
    cat_to_names: dict[str, list[str]] = {}
    for s in existing_skills:
        if s.category and s.name:
            cat_to_names.setdefault(s.category, []).append(s.name)

    # No categories to match against → append everything under "Other".
    if not cat_to_names:
        return existing_skills + [
            Skill(name=kw, category="Other", source_text="keyword_integration")
            for kw in unique_new
        ]

    categories = list(cat_to_names.keys())
    member_names = [n for c in categories for n in cat_to_names[c]]

    try:
        member_vecs = _embed(member_names)   # normalized (M, d)
        kw_vecs = _embed(unique_new)         # normalized (K, d)
    except Exception:
        # Embedding unavailable → keep keywords but don't guess categories.
        return existing_skills + [
            Skill(name=kw, category="Other", source_text="keyword_integration")
            for kw in unique_new
        ]

    # Per-category centroid = renormalized mean of its members' vectors.
    centroids: dict[str, np.ndarray] = {}
    offset = 0
    for c in categories:
        n = len(cat_to_names[c])
        vecs = member_vecs[offset:offset + n]
        offset += n
        centroid = vecs.mean(axis=0)
        norm = float(np.linalg.norm(centroid))
        centroids[c] = centroid / norm if norm > 0 else centroid

    seen = set(existing_names_lower)
    additions: list[Skill] = []
    for kw, kwv in zip(unique_new, kw_vecs):
        if kw.lower() in seen:
            continue
        best_cat, best_sim = "Other", -1.0
        for c in categories:
            sim = _cosine_sim(kwv, centroids[c])
            if sim > best_sim:
                best_sim, best_cat = sim, c
        category = best_cat if best_sim >= _CATEGORY_SIM_THRESHOLD else "Other"
        additions.append(Skill(name=kw, category=category, source_text="keyword_integration"))
        seen.add(kw.lower())

    return existing_skills + additions


def _compute_keyword_coverage(resume_text: str, jd: JobDescription) -> float:
    """Fraction of importance>=2 JD keywords present in the resume text."""
    high_kw = [k.term.lower() for k in jd.keywords if k.importance >= 2]
    if not high_kw:
        return 1.0
    text_lower = resume_text.lower()
    present = [k for k in high_kw if k in text_lower]
    return round(len(present) / len(high_kw), 2)


def _tailor_projects(
    projects: list[ProjectEntry],
    relevance_map: ExperienceRelevanceMap,
    jd: JobDescription,
    keyword_limit: int = 4,
    used_keywords: "set[str] | None" = None,
    project_scores: "dict[int, float] | None" = None,
    model: str = _FAST_MODEL,
) -> tuple[list[ProjectEntry], list[BulletChange]]:
    """
    Lightly tailor project bullets for moderately relevant projects only.
    Projects below _PROJECT_TAILOR_THRESHOLD are passed through unchanged.
    Keywords already used in experience bullets are excluded to prevent duplicates.
    Returns (modified project list, change audit entries).
    """
    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    already_used = {k.lower() for k in (used_keywords or set())}
    # Exclude keywords already used in experience bullets
    target_kws = [
        kw for kw in list(dict.fromkeys(high_kw + all_kw))[:keyword_limit]
        if kw.lower() not in already_used
    ]

    proj_scores = project_scores or {
        e.entry_index: e.overall_score
        for e in relevance_map.scored_entries
        if e.entry_type == "project"
    }

    # Collect all eligible project bullets for global assignment
    eligible: list[tuple[int, int, str]] = []  # (proj_i, b_i, text)
    eligible_proj_indices: list[int] = []
    for i, proj in enumerate(projects):
        if proj_scores.get(i, 0.0) >= _PROJECT_TAILOR_THRESHOLD and proj.bullets:
            for b_i, b in enumerate(proj.bullets[:3]):
                eligible.append((i, b_i, b.text))
            eligible_proj_indices.append(i)

    proj_kw_assignments = _assign_keywords_to_bullets(target_kws, eligible)

    # Build ONE global queue of every eligible project bullet, then rephrase them
    # all in a single batched call (was one call per project — the priciest-scaling
    # loop in the pipeline). Each item carries its project name for context.
    queue: list[tuple[int, int]] = []  # (proj_i, b_i) in batch order
    batch_items: list[tuple[str, str, list[str]]] = []  # (project_name, text, keywords)
    for i in eligible_proj_indices:
        proj = projects[i]
        for b_i, b in enumerate(proj.bullets[:3]):
            queue.append((i, b_i))
            batch_items.append((proj.name, b.text, proj_kw_assignments.get((i, b_i), [])))

    batch_results = _rephrase_project_bullets_batch(batch_items, model=model)
    rephrase_map: dict[tuple[int, int], tuple[str, list[str]]] = {}
    for qi, key in enumerate(queue):
        if qi < len(batch_results):
            rephrase_map[key] = batch_results[qi]

    all_changes: list[BulletChange] = []
    tailored_projects: list[ProjectEntry] = []

    for i, proj in enumerate(projects):
        if i not in eligible_proj_indices:
            tailored_projects.append(proj)
            continue

        new_bullets: list[Bullet] = []
        for b_i, orig_bullet in enumerate(proj.bullets[:3]):
            revised, kws_added = rephrase_map.get((i, b_i), (orig_bullet.text, []))
            change_reason = "keyword_integration" if revised != orig_bullet.text else "unchanged"
            all_changes.append(BulletChange(
                original_text=orig_bullet.text,
                revised_text=revised,
                change_reason=change_reason,
                keywords_added=kws_added,
            ))
            new_bullets.append(Bullet(text=revised, source_text=orig_bullet.source_text))

        new_bullets.extend(proj.bullets[3:])
        tailored_projects.append(ProjectEntry(
            name=proj.name,
            description=proj.description,
            technologies=proj.technologies,
            url=proj.url,
            date=proj.date,
            bullets=new_bullets,
            source_text=proj.source_text,
            relevance_score=proj.relevance_score,
        ))

    return tailored_projects, all_changes


def tailor_resume(
    profile: CandidateProfile,
    jd: JobDescription,
    relevance_map: ExperienceRelevanceMap,
    raw_score: int = 100,
    bullet_model: str = _QUALITY_MODEL,
    project_model: str = _FAST_MODEL,
    normalize_output: bool = True,
) -> TailoredResume:
    """Build a tailored resume from the profile and relevance scores.

    raw_score controls keyword injection aggressiveness:
      < 40  → top-3 keywords only (clear mismatch, output reflects reality)
      40-54 → top-6 keywords (moderate mismatch)
      ≥ 55  → top-10 keywords (standard tailoring)
    """
    # Tiered keyword limit: fewer keywords for mismatched profiles so the
    # output PDF naturally reflects the lower suitability score
    if raw_score < 40:
        keyword_limit = 3
    elif raw_score < 55:
        keyword_limit = 6
    else:
        keyword_limit = 10

    keyword_budget = [_MAX_KEYWORD_INTEGRATIONS]

    # Compute cross-block keyword frequency cap.
    # The batched experience call also returns the summary (Opt 5).
    tailored_experiences, summary = _select_and_tailor_experiences(
        profile, relevance_map, jd, keyword_budget,
        keyword_limit=keyword_limit,
        model=bullet_model,
    )

    # Fall back to a standalone summary call only if the folded one came back empty
    # (e.g. no experience bullets were rephrased, or the model omitted the field).
    if not summary:
        summary = _generate_summary(
            profile, jd, tailored_experiences, model=bullet_model
        )

    # Collect experience bullet changes for the audit trail
    exp_changes: list[BulletChange] = []
    for te in tailored_experiences:
        exp_changes.extend(tb.change for tb in te.bullets)

    # Collect keywords already used in experience bullets so projects don't repeat them
    exp_used_keywords: set[str] = set()
    for change in exp_changes:
        exp_used_keywords.update(k.lower() for k in change.keywords_added)

    # Rank before selecting: the project section should contain the work most
    # relevant to this role, not merely the first projects in the source file.
    ranked_projects = _rank_project_candidates(profile, relevance_map)
    selected_projects = ranked_projects[:2]
    candidate_projects = [
        project.model_copy(update={"relevance_score": score})
        for project, score in selected_projects
    ]
    project_scores = {
        local_index: score
        for local_index, (_project, score) in enumerate(selected_projects)
    }
    if len(ranked_projects) > 2:
        used = _estimate_chars(
            summary, tailored_experiences, profile.education,
            profile.skills, candidate_projects, profile.leadership_items, profile.awards,
        )
        third_project, third_score = ranked_projects[2]
        extra = _project_chars(third_project)
        if (used + extra) <= _PAGE_CAPACITY_CHARS * _PAGE_FILL_HARD_LIMIT:
            project_scores[len(candidate_projects)] = third_score
            candidate_projects.append(third_project)
            candidate_projects[-1] = candidate_projects[-1].model_copy(
                update={"relevance_score": third_score}
            )

    # Tailor project bullets — exclude keywords already used in experience bullets
    projects, proj_changes = _tailor_projects(
        candidate_projects, relevance_map, jd,
        keyword_limit=min(4, keyword_limit),
        used_keywords=exp_used_keywords,
        project_scores=project_scores,
        model=project_model,
    )

    # ── Fill pass: expand project bullets when page is under soft target ─────
    # Profiles with sparse projects (few or short original bullets) can land at
    # ~70% page fill. We generate extra grounded bullets per project until we
    # reach the soft target or exhaust per-project capacity (3 bullets max each).
    estimated = _estimate_chars(
        summary, tailored_experiences, profile.education,
        profile.skills, projects, profile.leadership_items, profile.awards,
    )
    underfilled = estimated < _PAGE_CAPACITY_CHARS * _PAGE_FILL_SOFT_TARGET
    # A relevant project gets two evidence-grounded bullets independently of
    # page fill. If the resume is still sparse, the same single batch call may
    # request a third bullet. The model may return fewer only when the source
    # cannot support a distinct, truthful claim.
    target_counts: dict[int, int] = {}
    for pi, proj in enumerate(projects):
        if underfilled:
            target_counts[pi] = 3
        elif project_scores.get(pi, 0.0) >= _PROJECT_TAILOR_THRESHOLD:
            target_counts[pi] = 2
        else:
            target_counts[pi] = len(proj.bullets)

    fill_requests = [
        (pi, proj, min(3, target_counts[pi]) - len(proj.bullets))
        for pi, proj in enumerate(projects)
        if min(3, target_counts[pi]) > len(proj.bullets)
    ]
    generated = (
        _generate_extra_project_bullets_batch(
            fill_requests, jd, model=project_model
        )
        if fill_requests else {}
    )

    hard_ceiling = int(_PAGE_CAPACITY_CHARS * _PAGE_FILL_HARD_LIMIT)
    remaining_budget = max(0, hard_ceiling - estimated)
    expanded: list[ProjectEntry] = []
    generated_changes: list[BulletChange] = []
    for pi, proj in enumerate(projects):
        candidates = generated.get(pi, [])
        required = max(
            0,
            2 - len(proj.bullets),
        ) if project_scores.get(pi, 0.0) >= _PROJECT_TAILOR_THRESHOLD else 0
        added: list[Bullet] = []
        for candidate_index, new_bullet in enumerate(candidates):
            cost = len(new_bullet.text)
            is_minimum = candidate_index < required
            if not is_minimum and cost > remaining_budget:
                break
            added.append(new_bullet)
            remaining_budget = max(0, remaining_budget - cost)
            generated_changes.append(BulletChange(
                original_text=new_bullet.source_text,
                revised_text=new_bullet.text,
                change_reason="project_expansion",
                keywords_added=[],
            ))

        expanded.append(proj.model_copy(update={"bullets": proj.bullets + added}))

    projects = expanded
    # ─────────────────────────────────────────────────────────────────────────

    # Combine all changes for the audit trail
    all_changes = exp_changes + proj_changes + generated_changes

    # ── Augment skills with newly integrated keywords ────────────────────────
    # Collect every keyword the LLM added across all experience + project bullets,
    # classify them into the resume's existing skill categories, and append any
    # that aren't already listed.  This keeps the skills section in sync with
    # what the bullets now reference.
    all_added_keywords: list[str] = []
    for change in all_changes:
        all_added_keywords.extend(change.keywords_added)
    # Canonicalize categories BEFORE augmenting: _add_keywords_to_skills assigns
    # each new keyword to the nearest existing category by embedding centroid, so
    # it should be choosing between canonical buckets, not the model's ad-hoc
    # labels. Normalizing again afterwards catches anything it filed under "Other"
    # and drops duplicates.
    augmented_skills = _add_keywords_to_skills(
        all_added_keywords, normalize_skills(profile.skills), jd
    )
    # ─────────────────────────────────────────────────────────────────────────

    # ── Presentation normalization ───────────────────────────────────────────
    # Selection above is relevance-driven, which is right. Presentation is
    # date-driven, which it was not: entries used to render in relevance order,
    # so two of four shipped samples broke reverse-chronological convention.
    # Dates are canonicalized here too, so one document never mixes "Jun 2022"
    # with "June 2022".
    if normalize_output:
        tailored_experiences = normalize_experiences(tailored_experiences)
        projects = normalize_projects(projects)
        education = normalize_education(profile.education)
        augmented_skills = normalize_skills(augmented_skills)
    else:
        education = profile.education
    # ─────────────────────────────────────────────────────────────────────────

    # Build full resume text for keyword coverage check.
    # Skills are deliberately EXCLUDED so the coverage score reflects only
    # real content improvement from bullet rewrites — not skills additions.
    # This makes the raw→tailored gap fully traceable to the changelog.
    full_text_parts = [summary]
    for te in tailored_experiences:
        full_text_parts.append(te.role_title)
        full_text_parts.extend(tb.text for tb in te.bullets)
    for proj in projects:
        full_text_parts.extend(b.text for b in proj.bullets[:3])
    full_text = " ".join(full_text_parts)

    keyword_coverage = _compute_keyword_coverage(full_text, jd)

    return TailoredResume(
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin,
        github=profile.github,
        location=profile.location,
        summary=summary,
        experiences=tailored_experiences,
        education=education,
        projects=projects,
        skills=augmented_skills,
        awards=profile.awards,
        leadership_items=profile.leadership_items,
        keyword_coverage=keyword_coverage,
        changes=all_changes,
    )
