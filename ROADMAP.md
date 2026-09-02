# ApplyEasy — Roadmap

**Plan of record.** Supersedes `AUDIT_REPORT.md` as the forward-looking document
(the audit remains the record of what was found on 2026-06-26; its still-open
items are folded into Track D below).

**Created:** 2026-08-25
**Last updated:** 2026-09-02 — Phase 3 complete; profile review and keyword canonicalization delivered
**Status legend:** ☐ open · ◐ in progress · ☑ done

---

## The problem this roadmap solves

The pipeline is linear, one-shot, and its quality checks are advisory only.
`validate()` computes 11 checks, a `passed` boolean, and `evidence_quality_flags`
— and nothing reads them. `validation.passed` is never branched on. The system
knows when it produced a weak resume and ships it anyway.

Compounding that, the cheapest model does the highest-leverage work: profile
extraction and JD analysis both run on `llama-3.1-8b-instant`, and every
downstream decision (relevance scores, keyword targets, the score the user sees)
is derived from those two outputs. The 70B model only polishes bullets on top of
whatever structure the 8B model produced. Every JSON parse failure silently
returns `{}`, so a blank extraction still completes as a "successful" run.

### Measured evidence (the four shipped gallery PDFs)

| | resume_01 | resume_02 | resume_03 | resume_04 |
|---|---|---|---|---|
| Body font size | 9.0pt | 8.64pt | **7.56pt** | 9.0pt |
| Name font size | 17pt | 17.28pt | **13.44pt** | 18pt |
| Bottom whitespace | 8.9% | 4.3% | 8.4% | 4.1% |
| Reverse-chronological | ✅ | ❌ | ❌ | ✅ |
| Third-person summary | ❌ | ❌ | ❌ | ❌ |

Nine defect classes, all reproduced in shipped output:

1. **Typography tracks content volume.** `render_resume_pdf` scales every `pt`
   value down to a 72% floor until one page fits. A wordy candidate gets 7.56pt
   Times; a terse one gets 9pt Helvetica. Two outputs of the same product do not
   look like the same product. Meanwhile resume_01 sits at full size with 71pt
   of dead space at the bottom — fit is being solved at the wrong end.
2. **Experience order is relevance order, not date order.** No sort exists
   anywhere; the template renders `relevance_map` order verbatim. 2 of 4 samples
   violate reverse-chronological convention.
3. **Every summary is third-person and opens with the candidate's name.**
   "Alex Rivera has experience as a Software Engineer… He brings…" — 4 of 4.
4. **Anti-fabrication rules degrade into vague hedges.** With no metrics in the
   source, the rewriter emits "a large volume of monthly transactions",
   "significantly reduce the release cycle". Bullet strength silently tracks
   source-metric density; the failure mode is filler, not an honest gap.
5. **Style rules are stated and unenforced.** "Vary action verbs" — resume_03
   opens 4 bullets with "Built", 3 with "Prepared".
6. **Date formats drift inside one document.** "Jun 2022" beside "June 2022";
   "Jun 2022" beside "2021–2023". Extraction rule 5 preserves input verbatim.
7. **Skill categories are free-text from the LLM**, so the Skills block header
   vocabulary changes run to run.
8. **Awards silently vanish** when `leadership_items` is non-empty
   (`base.html` renders one *or* the other).
9. **The cover letter is visually second-class**: one CSS file, ignores
   `template_id`, no one-page fit, `temperature=0.4`, and a prohibited-phrase
   list that disagrees with the validator's.

### And on raw input

`document_ingestion_engine` computes a `sections{}` map — and the profile builder
ignores it entirely except for `summary`. The section-splitting apparatus is dead
signal. Worse, `_estimate_confidence()` scores extraction quality by *counting
recognized section headers*, and that number becomes `extraction_confidence`,
which is 25% of the headline score shown to the user. A freeform paste is
penalized for its formatting, not its content. No gap detection exists: no "this
role has no dates", no "this bullet has no outcome".

---

## Decisions taken (2026-08-25)

| Decision | Choice |
|---|---|
| Pro/Standard coexistence | **Separate quality profile.** One codebase, a `PipelineProfile` selected per run. Standard stays fast and cheap; Pro turns every knob up. Deterministic fixes land in **both** tiers — they cost nothing. |
| Input standardization | **Normalize + review screen.** Keep the freeform paste, add a normalization pass into a canonical profile document, then let the user review and correct before generation. |
| Pro budget | **~8–12 LLM calls, ≤45s.** 70B on extraction and JD analysis, plus one repair loop. No N-best sampling, no separate judge model. |
| Pro features | Cover letter revived · multi-variant output · editable review + targeted regenerate. |
| Relevant project depth | **At least two grounded bullets per selected project scoring ≥0.28.** This is a content-quality floor, not a page-fill side effect. If source evidence cannot support a distinct second claim, generation returns fewer and validation explicitly flags the project rather than fabricating one. |
| Bullet creative range | **Editorial creativity, factual conservatism.** Prompts vary evidence angle (architecture, implementation, integration, reliability/quality, grounded user value), opening verbs, and sentence structure. Creativity never licenses invented tools, metrics, scope, ownership, or outcomes. |

**Budget reconciliation:** multi-variant output is implemented as *composition
strategies over the same grounded content* (different section ordering and
emphasis rendered from one tailored resume), so variants cost **zero** additional
LLM calls and fit inside the 8–12 budget. Projected Pro run: normalization 1 +
extraction 1 + JD analysis 1 + bullet rewrite 1 + project bullets 1 + fill pass
(conditional) 1 + repair (conditional) 1 + cover letter 2 = **9–10 calls.**

---

## Track A — Deterministic quality layer (both tiers, no LLM cost)  — ✅ COMPLETE 2026-08-25

Everything here is free: pure code, no API calls. Defects 2, 6, 7 and 8 are fixed
outright; defects 3 and 5 are now prompt-corrected and *detected*, with automatic
repair landing in B5. Ships first because it raises Standard's floor immediately.

**Delivered:** `backend/src/normalization/{dates,ordering,skills}.py`,
`backend/src/validation/style_rules.py`, 34 new tests (84 total, all green).
Presentation normalization is applied in **both** `tailor_resume` and
`render_resume_pdf` — the renderer is the last common path, so no caller can
emit a PDF with relevance-ordered entries or mixed date formats.

- ☑ **A1. `backend/src/normalization/dates.py`** — parse the date formats seen in
  the wild ("Jun 2022", "June 2022", "06/2022", "Summer 2022", "2021–2023",
  "Present") into a canonical `(year, month)` sort key plus a single rendered
  format. One format per document, always.
- ☑ **A2. `backend/src/normalization/ordering.py`** — select entries by relevance
  (unchanged), then **present** them reverse-chronologically. Applies to
  experiences, education, and projects. This is the split that fixes defect 2
  without weakening relevance-based selection.
- ☑ **A3. `backend/src/normalization/skills.py`** — controlled category
  vocabulary (Languages, Frameworks & Libraries, Tools & Platforms, Data &
  ML, Domain) with a mapping layer, replacing free-text LLM categories.
  Deterministic category ordering in the rendered block.
- ☑ **A4. Verb-variety + hedge-phrase detectors** in `quality_validator` —
  turn the unenforced prompt rules into checks that the repair loop can act on.
  Hedge list: "a large volume of", "a large number of", "significantly",
  "various", "multiple" used as a metric substitute.
- ☑ **A5. Fix the awards/leadership template bug** (`base.html`) — render both
  sections when both exist.
- ☑ **A6. First-person-implied summary** — the candidate's name is no longer
  passed into either summary prompt (supplying it is what produced "Alex Rivera
  has experience as a..."), and both prompts now carry explicit VOICE rules.
  Detection is deterministic (`opens_with_name`, `has_third_person_pronoun`);
  **automatic repair is deferred to B5**. Regex-rewriting the prose here would
  trade a convention defect for a grammar defect — an LLM should do the rewrite.

## Track B — Pro pipeline  — ◐ PHASE 3 COMPLETE 2026-09-02

- ☑ **B1. `PipelineProfile`** (`backend/src/pipeline/profiles.py`) — per-run
  config: model per stage, repair loop on/off, normalization on/off, cover
  letter on/off, variant count. `standard` and `pro` presets. Threaded from
  `GenerateRequest.tier` → API validation → `run_pipeline()` → extraction, JD
  analysis, resume rewriting, project generation, normalization, and repair.
- ☑ **B2. Input normalization pass** — raw text → canonical profile document,
  with explicit gap detection (missing dates, bullet-less roles, outcome-less
  bullets) surfaced as structured findings rather than silently absorbed.
- ☑ **B3. Review screen** — frontend step between upload and JD entry showing the
  extracted profile as editable structured fields, with gaps flagged. Corrections
  feed back into the session before generation.
- ☑ **B4. 70B extraction + JD analysis** under the Pro profile, with
  **keyword canonicalization** (collapse "React"/"React.js"/"ReactJS" to one
  canonical term) so coverage metrics stop double-counting.
- ☑ **B5. Repair loop** — after `validate()`, route repairable flags (verb
  repetition, hedges, redundancy, generic phrases, thin evidence) back as one
  targeted rewrite call carrying the specific complaint per bullet. Max 1 pass,
  then re-validate. **This is the change that makes validation mean something.**
- ☑ **B6. Fail loudly on empty structured input stages** — candidate extraction
  retries its split fallback, then raises a user-safe `ProfileExtractionError`
  instead of completing with a blank profile; unusable JD analysis raises
  `JobAnalysisError`. The orchestrator distinguishes these expected failures
  from internal errors. Local rewrite parse failures remain safe degradations:
  they preserve original content, and the validation/repair path catches weak
  results rather than failing an otherwise usable run. Closes audit #13.
- ☐ **B7. Cover letter revival** — template-matched to the resume's
  `template_id`, one-page fit, `temperature=0`, single shared prohibited-phrase
  list. Closes audit #11.
- ☐ **B8. Multi-variant output** — 2–3 composition strategies over one tailored
  resume; user picks. Zero extra LLM calls.
- ☐ **B9. Editable review + targeted regenerate** — edit one bullet, re-run just
  that bullet.

## Track C — Render engine, page fit, format consistency  — ◐ SPIKE COMPLETE 2026-08-25

**Decision: replace xhtml2pdf with RenderCV + Typst.** Spiked head-to-head on
five fixtures of increasing content volume, measured the same way as the gallery:

| Fixture | xhtml2pdf body/name | RenderCV+Typst body/name | renders |
|---|---|---|---|
| sparse | 9.0 / 17.0pt | **10.0 / 20.0pt** | 1 |
| typical | 9.0 / 17.0pt | **10.0 / 20.0pt** | 1 |
| dense | 9.0 / 17.0pt | **10.0 / 20.0pt** | 1 |
| oversized | 7.42 / 14.02pt | **9.0 / 20.0pt** (1 trim) | 7 |
| extreme | **6.95 / 13.13pt** | **9.0 / 20.0pt** (4 trims) | 10 |

Typst holds identical typography across every volume; xhtml2pdf degrades to
6.95pt body text and a 13.13pt name. 0.3s for the common case, 3.4s worst case
— comfortably inside the Pro latency budget. Typst ships as a bundled binary
(no LaTeX, no system deps) and `render_full_template(model, "typst")` gives back
source, so we keep full control of compilation.

- ☑ **C1. Trim-before-shrink** — delivered as a *fitting ladder*: named typed
  design changes (whitespace → margins → body text in small steps), then content
  trimming below the 9pt floor. The name and section titles never shrink.
  Trimming drops trailing projects, then the lowest `relevance_score` bullet,
  then trailing experiences — measured, not guessed.
- ☑ **C2. Fitting search is O(trims + rungs)** — the naive "re-walk the ladder
  after every trim" cost 25 renders on a five-experience resume; try-baseline →
  trim-at-floor → walk-up costs 10, and the common case stays at **1**.
- ☑ **C3a. `letter-spacing`** — moot: the `getSize: Not a float '0.05em'` failure
  is an xhtml2pdf limitation that does not exist in Typst.
- ☐ **C5. Wire into the orchestrator** — `render_resume_pdf_rendercv` exists and
  is tested; `orchestrator` still calls the xhtml2pdf path. Needs the
  `template_id` → theme mapping and a decision on retiring the Jinja templates.
- ☐ **C6. Re-render the gallery** through the new engine (needs `GROQ_API_KEY`).
- ☐ **C3. Single source of truth for page-capacity constants** — 3600 / 3200 /
  380 still disagree across three modules, and `_PAGE_CAPACITY_CHARS` in the
  tailoring engine is now calibrated against the *old* engine's density.
- ☐ **C4. Score parity** — `scoreUtils.ts` reimplements the headline score with
  different weights than `compute_raw_suitability_v2`. Closes audit #20.

**Delivered:** `backend/src/rendering/rendercv_renderer.py`,
`backend/tests/test_rendercv_renderer.py` (25 tests; 109 total, all green),
deps added to `backend/pyproject.toml`.

**Adapter bugs the content-parity check caught** (all silently wrong output, not
errors) — kept as regression tests: a lone graduation date rendering as
"May 2022 – present"; skills bypassing `normalize_skills` and producing 8 ad-hoc
categories instead of 4 canonical ones; RenderCV's "4 years 2 months" CV time
spans; and its stock month abbreviations mixing widths (`Jan`/`June`/`Sept`),
which reintroduces the exact date drift Track A removed.

## Cross-track content generation — ☑ FOUNDATION DELIVERED 2026-08-25

- ☑ Projects are ranked by JD relevance before the two-project selection cap;
  source order is now only the stable tie-breaker.
- ☑ Relevant selected projects target a two-bullet minimum before optional page
  fill. Sparse resumes may request a third bullet in the same batched call.
- ☑ Generated project bullets retain their real project source text in the audit
  trail instead of the placeholder `"generated"`.
- ☑ Experience rewrite, project rewrite, project expansion, and Pro repair prompts
  all share the creative-range policy: distinct evidence angles, varied verbs,
  and varied sentence architecture under strict grounding rules.
- ☑ Deterministic quality checks now include project bullets for generic phrases,
  redundancy, thin evidence, repeated verbs, vague quantifiers, truthfulness,
  keyword coverage, and the relevant-project depth floor.

## Track D — Carried-over audit items

Still open from `AUDIT_REPORT.md`, verified against the code on 2026-08-25:

- ☐ **D1. PII purge from git history** *(was P0)* — `origin/main` matches local;
  183 files under `outputs/`, `test_profiles/`, `test_jobs/` remain in history and
  were only removed in `8dcf240`. Needs history rewrite + force-push, and a check
  of whether the GitHub repo is public.
- ☐ **D2. Packaging** *(audit #6, half-fixed)* — the documented `pytest
  backend/tests` still fails with `ModuleNotFoundError: No module named
  'backend'`; only `python -m pytest backend/tests` works. `pip install -e .`
  from `backend/` installs zero packages (`include = ["backend*"]` matches
  nothing there). Fix: move `pyproject.toml` to repo root or add a root conftest.
- ☐ **D3. Pipeline-level deadline** *(audit #2 follow-up)* — per-call Groq
  timeouts exist; nothing marks a stalled run failed.
- ☐ **D4. Orphaned-run reconciliation** *(audit #17)*.
- ☐ **D5. Batched embeddings** *(audit #15)* + **model warm-up at startup**
  *(#16)* — matters more once Pro raises per-run latency.
- ◐ **D6. `.env.example`, CI, ESLint config** *(#18, #19)* — `backend/.env.example`
  added 2026-08-25 (documents the three live vars, and previews the planned ones
  under an explicit not-yet-wired fence). Still open: no CI, and `npm run lint`
  is non-functional because no ESLint config file exists in `frontend/`.
- ☐ **D7. CORS prod origins** *(#21)*, blocking cross-origin deploy.

---

## Sequencing

**Phase 1 — ☑ complete:** Track A end to end. Free, benefits both tiers, fixes
five defect classes, and gives the repair loop something to act on.
**Phase 2 — ☑ complete:** B1 → B6 → B5 (profile plumbing, honest failures,
one complaint-directed repair pass), plus the new project-depth and
creative-range decisions above.
**Phase 3 — ☑ complete:** B2 → B3 provides an ownership-protected structured
review API and four-step frontend flow; user corrections are serialized into a
canonical evidence document before generation. B4's Pro 70B model routing was
already delivered with B1; keyword aliases are now canonicalized and deduped
before matching and coverage scoring. Verified with 124 backend tests and a
frontend production build on 2026-09-02.
**Phase 4 — next:** Track C (page fit), then B7 → B8 → B9.
**Ongoing:** Track D, prioritising D1 and D2.
