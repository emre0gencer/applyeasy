# AI Resume & Cover Letter Tailoring System

A constrained-generation pipeline that tailors resumes and cover letters to job descriptions without hallucinating — every output claim traces to the candidate's verified source material.

## Architecture

```
Browser (React + Vite)
  ↕ REST API
FastAPI Backend
  ↓ Background Task
Pipeline:
  DocumentIngestionEngine → CandidateProfileBuilder → JobDescriptionAnalyzer
  → RelevanceRanker → ResumeTailoringEngine → CoverLetterGenerator
  → QualityValidator → PDFRenderer
```

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- An Anthropic API key

### Backend

```bash
cd backend
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=your_key_here
uvicorn backend.src.api.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Run Tests

```bash
cd backend
pytest tests/ -v
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Your Anthropic API key |
| `DB_PATH` | `resume_tool.db` | SQLite database file path |
| `OUTPUT_DIR` | `outputs` | Directory for generated PDFs |

## Pipeline Steps

1. **extracting_profile** — PDF/text ingestion + Claude Haiku extraction → `CandidateProfile`
2. **analyzing_job** — Claude Haiku extraction → `JobDescription`
3. **scoring_relevance** — sentence-transformers cosine similarity → `ExperienceRelevanceMap`
4. **tailoring_resume** — selection + constrained Haiku rephrasing + Sonnet summary → `TailoredResume`
5. **generating_cover_letter** — Sonnet alignment + Sonnet generation → `TailoredCoverLetter`
6. **rendering_pdfs** — Jinja2 + WeasyPrint → `resume.pdf`, `cover_letter.pdf`, `change_summary.json`

## Truthfulness Constraints

- Every extracted entity carries a `source_text` field with verbatim source material
- Bullet rephrasing uses `temperature=0` and is instructed never to add new claims
- Post-generation entity matching checks that named entities in outputs exist in source
- Change summary logs every modification — downloadable by the user

## Estimated Cost Per Run

~$0.05–0.15 depending on resume/JD length (Haiku for extraction, Sonnet for generation).

## Project Structure

```
backend/
  src/
    api/            FastAPI routes
    models/         Pydantic schemas (schemas.py — built first)
    ingestion/      PDF + text extraction
    extraction/     LLM → CandidateProfile
    analysis/       LLM → JobDescription
    matching/       Embedding-based relevance ranking
    generation/     Resume tailoring + cover letter
    validation/     Quality checks
    rendering/      Jinja2 + WeasyPrint PDF output
    pipeline/       Orchestrator
    storage/        SQLAlchemy + SQLite
  templates/        HTML/CSS resume + cover letter templates
  tests/            pytest suite with mocked LLM calls
frontend/
  src/
    api/            Typed fetch client
    components/     ProfileStep, JobDescriptionStep, GeneratingStep, ResultsStep
```
