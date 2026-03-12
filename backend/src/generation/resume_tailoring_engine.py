"""
ResumeTailoringEngine — selection + reorder + constrained LLM rephrasing.

Selection logic is deterministic. Rephrasing uses a single batched Groq call.
Summary generation uses llama-3.3-70b-versatile for quality.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from groq import Groq

from backend.src.analysis.evidence_extractor import extract_evidence
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

_client: "Groq | None" = None

_FAST_MODEL = "llama-3.1-8b-instant"
_QUALITY_MODEL = "llama-3.3-70b-versatile"


def _get_client() -> "Groq":
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
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


def _distribute_entry_keywords(
    candidate_kws: list[str],
    num_bullets: int,
    kw_block_counts: dict[str, int],
    max_blocks_per_kw: int,
    kw_per_bullet: int = 2,
) -> list[list[str]]:
    """
    Assign unique keywords to each bullet in one entry (experience or project).

    Rules:
    - Each keyword appears at most ONCE within this entry (no intra-block repetition).
    - Each keyword is only eligible if it has appeared in fewer than
      max_blocks_per_kw blocks so far (cross-block frequency cap).
    - After assignment, increments kw_block_counts for keywords used.

    Returns a per-bullet list of keyword assignments.
    """
    # Only keywords still under the cross-block frequency cap
    available = [kw for kw in candidate_kws
                 if kw_block_counts.get(kw, 0) < max_blocks_per_kw]

    used_in_entry: set[str] = set()
    assignments: list[list[str]] = []

    for _ in range(num_bullets):
        # Keywords not yet assigned in this entry
        remaining = [kw for kw in available if kw not in used_in_entry]
        assigned = remaining[:kw_per_bullet]
        used_in_entry.update(assigned)
        assignments.append(assigned)

    # Update cross-block counts for all keywords used anywhere in this entry
    for kw in used_in_entry:
        kw_block_counts[kw] = kw_block_counts.get(kw, 0) + 1

    return assignments


def _rephrase_bullets_batch(
    bullets: list[tuple[str, list[str], "BulletEvidence | None"]],
    role_title: str,
    domain_signals: "list[str] | None" = None,
    evidence_style: str = "",
) -> list[tuple[str, list[str]]]:
    """
    Single Groq call to rewrite ALL bullets using evidence-grounded, recruiter-useful prompting.

    bullets = list of (original_text, keywords_to_try, evidence_signals_or_None)
    Returns list of (revised_text, keywords_added).

    v2 change: The primary rewrite objective is to surface concrete evidence —
    scope, complexity, ownership, and deliverable specificity.
    Keywords are secondary: integrated only where they fit the evidence naturally.
    """
    if not bullets:
        return []

    domain_context = ""
    if domain_signals:
        domain_context = f"\nRole domain focus: {', '.join(domain_signals[:3])}"
    if evidence_style:
        domain_context += f"\nEvidence this role values: {evidence_style}"

    system = (
        "You are a senior technical resume writer. Your goal is to make each bullet "
        "more informative, more specific, and more useful to a recruiter — "
        "by surfacing real evidence of what was done, how it was done, and what it produced.\n\n"

        "PRIMARY OBJECTIVE — EVIDENCE FIRST:\n"
        "Surface concrete evidence in each bullet:\n"
        "  - Scope: end-to-end, user-facing, production-ready, multi-step, workflow-critical\n"
        "  - Complexity: schema design, validation logic, API integration, state management, "
        "evaluation workflows, debugging, observability\n"
        "  - Ownership: designed, built, implemented, validated, optimized, deployed\n"
        "  - Deliverable: named system/API/pipeline/schema/workflow/layer\n"
        "Use the provided evidence_signals to understand what's already in the bullet "
        "and bring it forward more clearly.\n\n"

        "GROUNDED QUANTIFICATION (use freely — these communicate value without inventing numbers):\n"
        "  - Structural scope: 'end-to-end', 'user-facing', 'transaction-oriented', 'production'\n"
        "  - Technical complexity: 'validation layer', 'API integration', 'evaluation workflow'\n"
        "  - Ownership clarity: 'designed', 'built', 'implemented from scratch'\n"
        "  - Deliverable specificity: 'REST API', 'data pipeline', 'schema with integrity constraints'\n\n"

        "KEYWORDS — SECONDARY:\n"
        "Integrate provided keywords only where they fit the evidence and add clarity. "
        "If a keyword does not fit the technical context of this bullet, SKIP IT. "
        "Never use keywords as padding. Never force a keyword where it sounds unnatural.\n\n"

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

        "ABSOLUTE PROHIBITIONS — Never invent:\n"
        "  - Percentages, counts, team sizes, latency numbers, revenue figures\n"
        "  - Tools, technologies, frameworks, or libraries not in the original bullet\n"
        "  - Scope claims ('large-scale', 'millions of') not grounded in the original\n"
        "  - Ownership levels ('led a team of 5') not stated in the original\n"
        "  - Outcomes or results not mentioned in the original\n"
        "  - Seniority indicators (led, managed) not present in the original\n\n"

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

    resp = _get_client().chat.completions.create(
        model=_QUALITY_MODEL,
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
            (r.get("revised_text", bullets[i][0]), r.get("keywords_added", []))
            for i, r in enumerate(results)
            if i < len(bullets)
        ]
    except (json.JSONDecodeError, AttributeError, IndexError):
        return [(text, []) for text, _, _ev in bullets]


def _rephrase_project_bullets(
    bullets: list[tuple[str, list[str]]],
    project_name: str,
) -> list[tuple[str, list[str]]]:
    """
    Evidence-grounded light-touch rephrasing for project bullets.
    Keywords integrated only where they fit naturally.
    Uses the fast model (lighter task than experience rephrasing).

    v2: Primary objective shifted from keyword integration to evidence surfacing.
    """
    if not bullets:
        return []

    system = (
        "You are a senior technical resume writer. Improve each project bullet to surface "
        "concrete evidence of what was built, how it worked, and what it delivered — "
        "while preserving the original scope and technical stack entirely.\n\n"
        "PRIMARY OBJECTIVE — EVIDENCE FIRST:\n"
        "  - Name the deliverable: system, API, pipeline, schema, workflow, application\n"
        "  - Surface what was technically interesting: validation, schema design, API integration, "
        "state management, evaluation, async logic\n"
        "  - Clarify ownership: designed, built, implemented, integrated, evaluated\n"
        "  - Indicate scope where visible: end-to-end, user-facing, production, multi-step\n\n"
        "KEYWORDS — SECONDARY:\n"
        "Incorporate the provided target keywords ONLY where they fit naturally and add clarity. "
        "If a keyword does not fit the project's technical context, skip it — do not force it.\n\n"
        "RULES:\n"
        "1. Do NOT invent tools, technologies, metrics, outcomes, or scope not in the original.\n"
        "2. Keep length close to the original (25-45 words). Do not bloat.\n"
        "3. Open with a strong past-tense action verb.\n"
        "4. Preserve the original technical stack and outcomes exactly.\n"
        "5. Prefer a denser, more informative bullet over a longer keyword-heavy one.\n"
        "Return ONLY valid JSON: "
        '{"results": [{"revised_text": str, "keywords_added": [str]}]}'
        " — one result per input bullet in the same order."
    )
    items = [
        {"index": i, "original": text, "keywords_to_try": kws, "project": project_name}
        for i, (text, kws) in enumerate(bullets)
    ]
    user_msg = f"Project: {project_name}\nBullets:\n{json.dumps(items)}"

    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
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
            (r.get("revised_text", bullets[i][0]), r.get("keywords_added", []))
            for i, r in enumerate(results)
            if i < len(bullets)
        ]
    except (json.JSONDecodeError, AttributeError, IndexError):
        return [(text, []) for text, _ in bullets]


def _generate_summary(
    profile: CandidateProfile,
    jd: JobDescription,
    selected_experiences: list[TailoredExperience],
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
        "RULES:\n"
        "1. Only reference background elements present in the provided profile data.\n"
        "2. Do NOT fabricate achievements, metrics, or skills not listed.\n"
        "3. No generic phrases: 'passionate', 'results-driven', 'team player', 'fast learner', "
        "'proven track record', 'excited to', 'eager to'.\n"
        "4. Maximum 85 words total. Output only the 2 sentences — no labels, no extra text."
    )
    user_msg = (
        f"Candidate name: {profile.name}\n"
        f"Recent roles: {exp_titles}\n"
        f"Skills: {skills_snippet}\n"
        f"Target role: {jd.role_title} at {jd.company_name or 'the company'}\n"
        f"Target keywords: {top_kw}\n"
        f"Seniority: {jd.seniority_level}"
        f"{domain_context}"
    )

    resp = _get_client().chat.completions.create(
        model=_QUALITY_MODEL,
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
    kw_block_counts: "dict[str, int] | None" = None,
    max_blocks_per_kw: int = 99,
) -> list[TailoredExperience]:
    """Select top experiences and tailor their bullets using a single batch LLM call."""
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

    # Collect bullets that need rephrasing in one pass
    # v2: rephrase_queue now includes evidence per bullet
    rephrase_queue: list[tuple[int, int, str, list[str], "BulletEvidence | None"]] = []
    per_exp_sorted: list[list[ScoredBullet]] = []

    for exp_i, scored_entry in enumerate(exp_entries):
        idx = scored_entry.entry_index
        if idx >= len(profile.experiences):
            per_exp_sorted.append([])
            continue

        # v2: sort by bullet_contribution_score (evidence-aware) instead of pure cosine sim
        sorted_bullets = sorted(
            scored_entry.scored_bullets,
            key=lambda sb: sb.bullet_contribution_score,
            reverse=True,
        )[:_MAX_BULLETS_PER_EXP]
        per_exp_sorted.append(sorted_bullets)

        if exp_i in padded_set:
            # Low-relevance padded entry: keep bullets unchanged, no keyword injection
            continue

        # Candidate keyword pool for this entry, high-importance first
        candidate_kws = list(dict.fromkeys(high_kw + all_kw))[:keyword_limit]

        # Distribute keywords across bullets: each bullet gets its own unique pair
        _kw_counts = kw_block_counts if kw_block_counts is not None else {}
        per_bullet_kws = _distribute_entry_keywords(
            candidate_kws, len(sorted_bullets), _kw_counts, max_blocks_per_kw
        )
        for b_i, sb in enumerate(sorted_bullets):
            # v2: attach evidence (from ranker if present, else extract on-the-fly)
            evidence = sb.evidence if sb.evidence is not None else extract_evidence(sb.bullet.text)
            rephrase_queue.append((exp_i, b_i, sb.bullet.text, per_bullet_kws[b_i], evidence))

    # Single batch call for all bullets needing rephrasing
    # v2: pass evidence context and JD domain signals to the evidence-constrained rewriter
    batch_inputs = [(text, kws, ev) for _, _, text, kws, ev in rephrase_queue]
    batch_results = (
        _rephrase_bullets_batch(
            batch_inputs, role_title,
            domain_signals=jd.domain_signals,
            evidence_style=jd.evidence_style,
        )
        if batch_inputs else []
    )

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
                change_reason = "keyword_integration" if keywords_added else "unchanged"
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

    return tailored_experiences


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


def _generate_extra_project_bullets(
    proj: ProjectEntry,
    n_new: int,
    jd: JobDescription,
    existing_bullets: list[str],
) -> list[Bullet]:
    """
    Generate up to n_new additional bullets for a project.
    Grounded exclusively in the project's source_text, description, technologies,
    and existing bullets — never invents new facts.
    Used only during the fill pass when the page is under the soft target.
    """
    if n_new <= 0:
        return []

    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    target_kws = list(dict.fromkeys(high_kw + all_kw))[:4]
    techs = ", ".join(proj.technologies[:6]) if proj.technologies else ""
    source_context = (proj.source_text or proj.description or "")[:600]

    system = (
        "You are a senior technical resume writer. Generate additional resume bullet points "
        "for the given project, grounded ONLY in the information explicitly provided "
        "(source description, technologies, existing bullets). "
        "Do NOT invent new tools, metrics, outcomes, or any claim not already implied.\n\n"
        "RULES:\n"
        "1. Each bullet must cover a distinct aspect not already described by the existing bullets.\n"
        "2. 30-50 words per bullet. Open with a strong past-tense action verb.\n"
        "3. Integrate the provided target keywords only where they fit naturally.\n"
        "4. Never duplicate or restate an existing bullet.\n"
        "5. If you cannot produce a grounded, distinct bullet, return fewer than requested.\n"
        "Return ONLY valid JSON: {\"bullets\": [\"bullet text\", ...]}"
    )
    existing_str = "\n".join(f"- {b}" for b in existing_bullets)
    user_msg = (
        f"Project: {proj.name}\n"
        f"Technologies: {techs}\n"
        f"Source description: {source_context}\n"
        f"Existing bullets:\n{existing_str}\n"
        f"Target role: {jd.role_title}\n"
        f"Target keywords to try: {target_kws}\n"
        f"Generate {n_new} additional bullet(s)."
    )

    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        raw = data.get("bullets", [])
        return [Bullet(text=b.strip(), source_text="generated") for b in raw[:n_new] if b.strip()]
    except (json.JSONDecodeError, AttributeError):
        return []


def _add_keywords_to_skills(
    keywords_added: list[str],
    existing_skills: list[Skill],
    jd: JobDescription,
) -> list[Skill]:
    """
    Classify newly integrated keywords into the resume's existing skill categories
    and return an augmented skills list.  Only genuine technical skills/tools/
    technologies are included; soft-skill terms and generic concepts are skipped.
    Already-present skills are never duplicated.
    """
    if not keywords_added:
        return existing_skills

    existing_names_lower = {s.name.lower() for s in existing_skills}
    # Deduplicate while preserving order
    unique_new = list(dict.fromkeys(k for k in keywords_added if k.lower() not in existing_names_lower))
    if not unique_new:
        return existing_skills

    existing_categories = list(dict.fromkeys(s.category for s in existing_skills if s.category))

    system = (
        "You are classifying technical keywords into skill categories for a resume skills section.\n\n"
        "For each keyword decide:\n"
        "1. Is it a genuine technical skill, tool, language, framework, platform, or methodology "
        "   worth listing in a skills section? (yes → include: true; no → include: false)\n"
        "2. Which existing category does it belong to? Use the closest match from the provided "
        "   category list. If none fit, use 'Other'.\n\n"
        "EXCLUDE: soft skills, action verbs, adjectives, vague concepts.\n"
        "INCLUDE: tools (Jira, Docker), languages (Java, C++), frameworks (Agile, Scrum), "
        "   platforms (AWS, GCP), protocols, libraries.\n"
        "Return ONLY valid JSON: "
        '{"assignments": [{"keyword": str, "category": str, "include": bool}]}'
    )
    user_msg = (
        f"Existing skill categories: {existing_categories}\n"
        f"Target role: {jd.role_title}\n"
        f"Keywords to classify: {unique_new}"
    )

    resp = _get_client().chat.completions.create(
        model=_FAST_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
        seen = set(existing_names_lower)
        additions: list[Skill] = []
        for a in data.get("assignments", []):
            kw = (a.get("keyword") or "").strip()
            cat = (a.get("category") or "Other").strip()
            include = a.get("include", False)
            if include and kw and kw.lower() not in seen:
                additions.append(Skill(name=kw, category=cat, source_text="keyword_integration"))
                seen.add(kw.lower())
        return existing_skills + additions
    except (json.JSONDecodeError, AttributeError, KeyError):
        return existing_skills


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
    kw_block_counts: "dict[str, int] | None" = None,
    max_blocks_per_kw: int = 99,
) -> tuple[list[ProjectEntry], list[BulletChange]]:
    """
    Lightly tailor project bullets for moderately relevant projects only.
    Projects below _PROJECT_TAILOR_THRESHOLD are passed through unchanged.
    Returns (modified project list, change audit entries).
    """
    high_kw = _get_high_importance_keywords(jd)
    all_kw = _get_all_keywords(jd)
    # Narrow keyword set — lighter touch than experience tailoring, capped by keyword_limit
    target_kws = list(dict.fromkeys(high_kw + all_kw))[:keyword_limit]

    proj_scores: dict[int, float] = {
        e.entry_index: e.overall_score
        for e in relevance_map.scored_entries
        if e.entry_type == "project"
    }

    all_changes: list[BulletChange] = []
    tailored_projects: list[ProjectEntry] = []

    for i, proj in enumerate(projects):
        score = proj_scores.get(i, 0.0)

        if score >= _PROJECT_TAILOR_THRESHOLD and proj.bullets:
            # Distribute keywords per-bullet to avoid intra-project repetition
            _kw_counts = kw_block_counts if kw_block_counts is not None else {}
            per_bullet_kws = _distribute_entry_keywords(
                target_kws, len(proj.bullets[:3]), _kw_counts, max_blocks_per_kw, kw_per_bullet=2
            )
            bullets_input = [(b.text, per_bullet_kws[i]) for i, b in enumerate(proj.bullets[:3])]
            rephrased = _rephrase_project_bullets(bullets_input, proj.name)

            new_bullets: list[Bullet] = []
            for orig_bullet, (revised, kws_added) in zip(proj.bullets[:3], rephrased):
                change_reason = "keyword_integration" if kws_added else "unchanged"
                all_changes.append(BulletChange(
                    original_text=orig_bullet.text,
                    revised_text=revised,
                    change_reason=change_reason,
                    keywords_added=kws_added,
                ))
                new_bullets.append(Bullet(text=revised, source_text=orig_bullet.source_text))

            # Keep bullets beyond first 3 unchanged
            new_bullets.extend(proj.bullets[3:])

            tailored_projects.append(ProjectEntry(
                name=proj.name,
                description=proj.description,
                technologies=proj.technologies,
                url=proj.url,
                date=proj.date,
                bullets=new_bullets,
                source_text=proj.source_text,
            ))
        else:
            tailored_projects.append(proj)

    return tailored_projects, all_changes


def tailor_resume(
    profile: CandidateProfile,
    jd: JobDescription,
    relevance_map: ExperienceRelevanceMap,
    raw_score: int = 100,
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
    # A keyword should appear in at most ceil(total_tailored_blocks / 2) blocks.
    # Count experiences above threshold + projects above project threshold.
    all_exp_scored = [e for e in relevance_map.scored_entries if e.entry_type == "experience"]
    proj_scored = {e.entry_index: e.overall_score
                   for e in relevance_map.scored_entries if e.entry_type == "project"}
    n_tailored_exp = min(_MAX_EXPERIENCES,
                         len([e for e in all_exp_scored if e.overall_score >= _ENTRY_THRESHOLD]))
    n_tailored_proj = sum(
        1 for i in range(min(len(profile.projects), 3))
        if proj_scored.get(i, 0.0) >= _PROJECT_TAILOR_THRESHOLD
    )
    total_tailored_blocks = max(n_tailored_exp + n_tailored_proj, 1)
    # ceil(total / 2): a keyword may appear in at most half the blocks
    max_blocks_per_kw = (total_tailored_blocks + 1) // 2

    # Shared mutable dict: tracks how many blocks each keyword has already appeared in
    kw_block_counts: dict[str, int] = {}

    tailored_experiences = _select_and_tailor_experiences(
        profile, relevance_map, jd, keyword_budget,
        keyword_limit=keyword_limit,
        kw_block_counts=kw_block_counts,
        max_blocks_per_kw=max_blocks_per_kw,
    )

    # Generate summary
    summary = _generate_summary(profile, jd, tailored_experiences)

    # Collect experience bullet changes for the audit trail
    exp_changes: list[BulletChange] = []
    for te in tailored_experiences:
        exp_changes.extend(tb.change for tb in te.bullets)

    # Include up to 2 projects; add a 3rd only if page budget allows
    candidate_projects = list(profile.projects[:2])
    if len(profile.projects) > 2:
        used = _estimate_chars(
            summary, tailored_experiences, profile.education,
            profile.skills, candidate_projects, profile.leadership_items, profile.awards,
        )
        extra = _project_chars(profile.projects[2])
        if (used + extra) <= _PAGE_CAPACITY_CHARS * _PAGE_FILL_HARD_LIMIT:
            candidate_projects.append(profile.projects[2])

    # Tailor project bullets — share kw_block_counts so cross-block cap is enforced globally
    projects, proj_changes = _tailor_projects(
        candidate_projects, relevance_map, jd,
        keyword_limit=min(4, keyword_limit),
        kw_block_counts=kw_block_counts,
        max_blocks_per_kw=max_blocks_per_kw,
    )

    # ── Fill pass: expand project bullets when page is under soft target ─────
    # Profiles with sparse projects (few or short original bullets) can land at
    # ~70% page fill. We generate extra grounded bullets per project until we
    # reach the soft target or exhaust per-project capacity (3 bullets max each).
    estimated = _estimate_chars(
        summary, tailored_experiences, profile.education,
        profile.skills, projects, profile.leadership_items, profile.awards,
    )
    if estimated < _PAGE_CAPACITY_CHARS * _PAGE_FILL_SOFT_TARGET:
        hard_ceiling = int(_PAGE_CAPACITY_CHARS * _PAGE_FILL_HARD_LIMIT)
        remaining_budget = hard_ceiling - estimated
        expanded: list[ProjectEntry] = []

        for pi, proj in enumerate(projects):
            current_count = len(proj.bullets)
            slots = 3 - current_count  # max 3 bullets total per project
            if slots <= 0 or remaining_budget <= 0:
                expanded.append(proj)
                continue

            existing_texts = [b.text for b in proj.bullets]
            new_bullets = _generate_extra_project_bullets(proj, slots, jd, existing_texts)

            added: list[Bullet] = []
            for nb in new_bullets:
                cost = len(nb.text)
                if remaining_budget - cost < 0:
                    break
                added.append(nb)
                remaining_budget -= cost

            if added:
                expanded.append(ProjectEntry(
                    name=proj.name,
                    description=proj.description,
                    technologies=proj.technologies,
                    url=proj.url,
                    date=proj.date,
                    bullets=proj.bullets + added,
                    source_text=proj.source_text,
                ))
            else:
                expanded.append(proj)

            if remaining_budget <= 0:
                expanded.extend(projects[pi + 1:])
                break

        projects = expanded
    # ─────────────────────────────────────────────────────────────────────────

    # Combine all changes for the audit trail
    all_changes = exp_changes + proj_changes

    # ── Augment skills with newly integrated keywords ────────────────────────
    # Collect every keyword the LLM added across all experience + project bullets,
    # classify them into the resume's existing skill categories, and append any
    # that aren't already listed.  This keeps the skills section in sync with
    # what the bullets now reference.
    all_added_keywords: list[str] = []
    for change in all_changes:
        all_added_keywords.extend(change.keywords_added)
    augmented_skills = _add_keywords_to_skills(all_added_keywords, profile.skills, jd)
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
        education=profile.education,
        projects=projects,
        skills=augmented_skills,
        awards=profile.awards,
        leadership_items=profile.leadership_items,
        keyword_coverage=keyword_coverage,
        changes=all_changes,
    )
