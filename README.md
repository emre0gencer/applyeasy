# ApplyEasy

An AI-powered resume tailoring app. Upload your profile, paste a job description, and get a tailored resume PDF — with every claim traceable to your source material, no hallucination.

## Architecture

```
Browser (React 18 + Vite)
  ↕ REST API
FastAPI Backend
  ↓ Normalize + editable profile review
  ↓ Background Task
Pipeline:
  DocumentIngestionEngine → CandidateProfileBuilder → JobDescriptionAnalyzer
  → RelevanceRanker → ResumeTailoringEngine → QualityValidator → PDFRenderer
```

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- A Groq API key (get one at console.groq.com)

### Backend

```bash
# Install dependencies (run from the backend/ directory)
cd backend
pip install -e ".[dev]"
cd ..

# IMPORTANT: run the server from the REPO ROOT, not from backend/.
# The code imports the package as `backend.src.*`, which only resolves when the
# repo root is the working directory. Default OUTPUT_DIR/DB_PATH also resolve
# relative to this directory.
export GROQ_API_KEY=your_key_here     # or put it in backend/.env
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
# Run from the REPO ROOT (tests import `backend.src.*`)
python -m pytest backend/tests -v
```

For live end-to-end cases, synthetic applicant/job pairs, artifact review, and
stage-by-stage diagnosis, see [TESTING_DEBUGGING_PIPELINE.md](TESTING_DEBUGGING_PIPELINE.md).

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | required | Your Groq API key |
| `DB_PATH` | `resume_tool.db` | SQLite database file path |
| `OUTPUT_DIR` | `outputs` | Directory for generated PDFs |

## Pipeline Steps

Before generation, the upload flow extracts a structured candidate profile,
flags missing dates/bullets/outcomes, and lets the user correct it. The confirmed
profile becomes the evidence source used by the generation pipeline.

1. **extracting_profile** — reviewed profile text + LLM extraction → `CandidateProfile`
2. **analyzing_job** — LLM extraction → `JobDescription`
3. **scoring_relevance** — sentence-transformers (`all-MiniLM-L6-v2`) cosine similarity → `ExperienceRelevanceMap`
4. **tailoring_resume** — constrained LLM rephrasing → `TailoredResume`
5. **validating** — deterministic quality checks → `ValidationResult`
6. **rendering_pdfs** — Jinja2 + xhtml2pdf → `resume.pdf`, `change_summary.json`

> Cover letter generation is currently disabled (`COVER_LETTER_ENABLED = False`).

## Truthfulness Constraints

- Every extracted entity carries a `source_text` field with verbatim source material
- Bullet rephrasing uses `temperature=0` and is instructed never to add new claims
- Post-generation entity matching checks that named entities in outputs exist in source
- Change summary logs every modification — downloadable by the user

## Project Structure

```
backend/
  src/
    api/            FastAPI routes
    models/         Pydantic schemas
    ingestion/      PDF + text extraction
    extraction/     LLM → CandidateProfile
    analysis/       LLM → JobDescription
    matching/       Embedding-based relevance ranking
    generation/     Resume tailoring
    validation/     Quality checks
    rendering/      Jinja2 + xhtml2pdf PDF output
    pipeline/       Orchestrator
    storage/        SQLAlchemy + SQLite
  templates/        HTML/CSS resume templates (classic, polished, traditional)
  tests/            pytest suite with mocked LLM calls
frontend/
  src/
    api/            Typed fetch client
    components/     LandingPage, JobDescriptionStep, GeneratingStep, ResultsStep
```
