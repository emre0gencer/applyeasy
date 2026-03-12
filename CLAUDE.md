# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend
```bash
cd backend
pip install -e ".[dev]"                          # Install dependencies
uvicorn backend.src.api.main:app --reload --port 8000  # Run dev server
pytest tests/ -v                                 # Run all tests
pytest tests/test_tailoring.py -v               # Run a single test file
```

### Frontend
```bash
cd frontend
npm install
npm run dev      # Vite dev server on :5173 (proxies /api → localhost:8000)
npm run build    # TypeScript compile + Vite bundle
npm run lint     # ESLint
```

### Environment
Copy `backend/.env` and set `GROQ_API_KEY`. The README mentions `ANTHROPIC_API_KEY` but it is not used — Groq is the LLM provider.

## Architecture

**ApplyEasy** is an AI-powered resume tailoring app. A user uploads a profile (PDF or text), pastes a job description, and the system produces a tailored resume PDF. Every claim traces back to source material — no hallucination.

### Request Flow

1. **POST /api/upload** — stores raw profile text in `SessionRecord` (SQLite)
2. **POST /api/generate** — creates `RunRecord`, launches `run_pipeline()` as a FastAPI `BackgroundTask`
3. **GET /api/status/{run_id}** — polled by frontend; returns progress step + final artifacts
4. **GET /api/download/{run_id}/{resume|cover-letter|summary}** — serves generated PDFs / JSON

### Pipeline (`backend/src/pipeline/orchestrator.py`)

Seven sequential steps, each updating `RunRecord.progress_step` in SQLite:

| Step | Module | Output type |
|------|--------|-------------|
| `extracting_profile` | `document_ingestion_engine` + `candidate_profile_builder` | `CandidateProfile` |
| `analyzing_job` | `job_description_analyzer` | `JobDescription` |
| `scoring_relevance` | `relevance_ranker` | `ExperienceRelevanceMap` (cosine similarity) |
| `tailoring_resume` | `resume_tailoring_engine` | `TailoredResume` |
| `generating_cover_letter` | `cover_letter_generator` | disabled (`COVER_LETTER_ENABLED = False`) |
| `validating` | `quality_validator` | `ValidationResult` |
| `rendering_pdfs` | `pdf_renderer` | PDF files written to `outputs/{run_id}/` |

### Frontend State Machine (`frontend/src/App.tsx`)

```
landing → job → generating → results
```

- **LandingPage**: uploads profile, calls `goToJob(sessionId, rawText)`
- **JobDescriptionStep**: captures JD, calls `goToGenerating(runId, jobDescription)`
- **GeneratingStep**: polls `/api/status` every ~1–2 s, calls `goToResults(status)` on completion
- **ResultsStep**: download links + `ChangeSummaryPanel` (audit trail of every bullet change)

Frontend uses inline `CSSProperties` everywhere — no CSS framework.

### PDF Rendering (`backend/src/rendering/pdf_renderer.py`)

- Engine: **xhtml2pdf** (pisa) — NOT WeasyPrint (the docstring is wrong)
- Templates: Jinja2 HTML + per-theme CSS
- **`display: flex` is not supported** — use `float: right` for date alignment; date span must appear first in HTML source order; use `overflow: hidden` as clearfix
- Three themes (`classic`, `polished`, `traditional`) share `base.html`; only the CSS file differs
- Page budget: ~3600 chars capacity, 0.93 hard limit; bullets capped at 380 chars; 3rd project only added if budget allows

### Database (`backend/src/storage/database.py`)

Two SQLite tables via SQLAlchemy ORM:
- **`SessionRecord`** — `session_id`, `raw_text`, `source_format`, `created_at`
- **`RunRecord`** — `run_id`, `session_id`, `status`, `progress_step`, PDF paths, `keyword_coverage`, `raw_suitability_score`, `error_message` (full traceback on failure), etc.

### Key file paths

| What | Where |
|------|-------|
| FastAPI app | `backend/src/api/main.py` |
| Pipeline orchestrator | `backend/src/pipeline/orchestrator.py` |
| Pydantic schemas | `backend/src/models/schemas.py` |
| PDF renderer | `backend/src/rendering/pdf_renderer.py` |
| Resume HTML template | `backend/templates/resume/base.html` |
| Theme CSS files | `backend/templates/resume/{classic,polished,traditional}.css` |
| API client (typed) | `frontend/src/api/client.ts` |

## Key Constraints & Gotchas

- **LLM is Groq**, not Anthropic. Set `GROQ_API_KEY`.
- **Cover letter is disabled** (`COVER_LETTER_ENABLED = False` in orchestrator). The code exists but is inactive.
- **xhtml2pdf has no flexbox** — always use floats + clearfix for multi-column layouts in templates.
- Bullet word target: 40–55 words. Char cap: 380. Page char capacity: 3600.
- `template_id` flows: `GenerateRequest.template_id` → `run_pipeline()` → `render_resume_pdf()`. Default is `"classic"`.
- `outputs/` and `test_profiles/` / `test_jobs/` directories are untracked but present locally.
