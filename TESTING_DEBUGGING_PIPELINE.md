# ApplyEasy testing and debugging pipeline

Use this playbook to test the resume pipeline with synthetic applicant/job pairs, isolate the stage that failed, and compare output quality without committing applicant data.

## Sample-data rule

All concrete applicant and job files must remain local and untracked:

- Applicant profiles: `test_profiles/*.txt`
- Job descriptions: `test_jobs/*.txt`
- Generated artifacts: `outputs/<run_id>/`

These root-level directories are ignored by `.gitignore`. Never move real or synthetic profiles into `backend/tests/fixtures/`, documentation, snapshots, or another tracked directory. Unit tests keep their minimal deterministic input inline instead.

Before committing, verify the rule:

```powershell
git ls-files -- test_profiles test_jobs outputs
git status --short --ignored test_profiles test_jobs outputs
```

The first command must print nothing. The second should prefix local samples and generated output with `!!`.

## Local sample pack

The local sample pack uses fictional people, employers, contact details, and project URLs. Real technology and provider names are retained so matching behavior is realistic. Files are intentionally untracked.

| ID | Applicant file | Primary job file | What it tests |
|---|---|---|---|
| P01/J01 | `qa_01_backend_high_fit.txt` | `qa_01_backend_platform.txt` | Clean extraction, strong relevance, grounded metrics, dense one-page rendering |
| P02/J02 | `qa_02_project_heavy_new_grad.txt` | `qa_02_junior_data_analyst.txt` | Project selection, limited work history, education/coursework parsing |
| P03/J01 | `qa_03_career_switcher_low_fit.txt` | `qa_01_backend_platform.txt` | Honest low-fit scoring and resistance to inventing backend skills |
| P04/J01 | `qa_04_messy_formatting.txt` | `qa_01_backend_platform.txt` | Inconsistent headings, dates, separators, duplicates, and sparse contact data |
| P05/J03 | `qa_05_evidence_trap.txt` | `qa_03_backend_skill_gap.txt` | Hallucination resistance when the JD names technologies absent from the profile |

Useful cross-pairs:

- P01/J03 should remain credible while leaving unsupported preferred skills missing.
- P02/J01 should score lower than P01/J01 even if both contain Python.
- P04/J01 should extract fewer details or lower confidence than P01/J01, but should not silently return a blank profile.
- P05/J03 must not claim Kubernetes, Terraform, AWS, Kafka, team leadership, on-call ownership, or invented metrics.

Treat exact scores and wording as nondeterministic. Compare ordering, source grounding, stage completion, and invariant violations rather than expecting byte-for-byte output.

## 1. Fast deterministic gate

Run this from the repository root. It uses mocked LLM responses and should not consume API quota.

```powershell
python -m pytest backend/tests -v
```

For quicker diagnosis, run the stage closest to the change:

```powershell
python -m pytest backend/tests/test_ingestion.py -v
python -m pytest backend/tests/test_extraction.py -v
python -m pytest backend/tests/test_evidence.py -v
python -m pytest backend/tests/test_tailoring.py -v
python -m pytest backend/tests/test_resume_repair.py -v
python -m pytest backend/tests/test_rendercv_renderer.py -v
```

Stop here if deterministic tests fail. A live model run adds noise and usually hides the simpler regression.

## 2. Start a local end-to-end run

Set `GROQ_API_KEY` in `backend/.env`, then start the API from the repository root:

```powershell
uvicorn backend.src.api.main:app --reload --port 8000
```

In a second PowerShell terminal, confirm health:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
```

You can paste the files through the UI at `http://localhost:5173`, or use the API script below. The cookie jar is required because sessions and runs are owner-scoped.

```powershell
$baseUrl = "http://localhost:8000"
$profilePath = "test_profiles/qa_01_backend_high_fit.txt"
$jobPath = "test_jobs/qa_01_backend_platform.txt"
$cookieJar = Join-Path $env:TEMP "applyeasy-test-cookies.txt"

$upload = curl.exe -sS -c $cookieJar -b $cookieJar `
  -F "text=<$profilePath" `
  "$baseUrl/api/upload" | ConvertFrom-Json

$payload = @{
  session_id = $upload.session_id
  job_description = Get-Content -Raw $jobPath
  template_id = "classic"
  include_cover_letter = $false
  tier = "standard"
} | ConvertTo-Json

$generation = curl.exe -sS -c $cookieJar -b $cookieJar `
  -H "Content-Type: application/json" `
  --data-binary $payload `
  "$baseUrl/api/generate" | ConvertFrom-Json

do {
  Start-Sleep -Seconds 2
  $status = curl.exe -sS -c $cookieJar -b $cookieJar `
    "$baseUrl/api/status/$($generation.run_id)" | ConvertFrom-Json
  $status | Select-Object status, progress_step, progress_message,
    extraction_confidence, raw_suitability_score, keyword_coverage,
    experience_count, validation_flags, error_message
} while ($status.status -in @("pending", "running"))

if ($status.status -eq "completed") {
  $artifactDir = Join-Path "outputs" $generation.run_id
  New-Item -ItemType Directory -Force $artifactDir | Out-Null
  curl.exe -sS -c $cookieJar -b $cookieJar `
    -o "$artifactDir/resume.downloaded.pdf" `
    "$baseUrl/api/download/$($generation.run_id)/resume"
  curl.exe -sS -c $cookieJar -b $cookieJar `
    -o "$artifactDir/change_summary.downloaded.json" `
    "$baseUrl/api/download/$($generation.run_id)/summary"
}
```

For a Pro run, set `tier = "pro"` and optionally `include_cover_letter = $true`. Standard-tier cover-letter requests should return HTTP 422 by design. Valid template IDs are `classic`, `polished`, and `traditional`.

## 3. Test matrix

Run this small matrix before a release or after prompt/model changes:

| Run | Pair | Tier/template | Expected result |
|---|---|---|---|
| Smoke | P01/J01 | Standard/classic | Completes; high relative fit; metrics stay unchanged |
| Quality | P01/J01 | Pro/polished | Completes; repair may reduce evidence/style flags |
| Project | P02/J02 | Standard/polished | Relevant projects appear without invented employment |
| Low fit | P03/J01 | Standard/traditional | Completes with a lower score than P01/J01; no fabricated tech |
| Parsing | P04/J01 | Standard/classic | Nonblank profile; honest omissions; no duplicated experience |
| Adversarial | P05/J03 | Pro/classic | Unsupported JD terms remain absent; truthfulness warnings are reviewed |

Add a three-template rendering pass with P01/J01 whenever HTML or CSS changes. Add a Standard/Pro comparison whenever model selection, normalization, validation, repair, or cover-letter logic changes.

## 4. Acceptance checklist

### API and stage behavior

- Upload returns a `session_id`; generation returns a `run_id`.
- Progress advances in order: extraction, job analysis, relevance, tailoring, optional cover letter, validation, rendering, completed.
- A failed run returns a safe user-facing `error_message`; the terminal contains the full traceback.
- The status response exposes extraction confidence, experience count, raw suitability score, keyword coverage, and validation flags when available.

### Grounding and content

- Every output number, proper noun, technology, credential, employer, and outcome exists in the applicant source.
- JD terminology is only added where applicant evidence supports it.
- Missing qualifications stay missing; the output does not imply exposure, ownership, scale, seniority, or results absent from the profile.
- Rewrites preserve the meaning of their `original_text`/`source_text`.
- Similar bullets are not duplicated merely to increase keyword coverage.
- The summary uses implied first person and does not open with the applicant's name.
- Bullets avoid generic filler, vague quantifiers, and repeated opening verbs within one entry.
- A selected project at relevance `>= 0.28` has two grounded bullets only when the source supports two distinct claims.

### Output and product rules

- `change_summary.json` is valid JSON and contains every changed bullet.
- `keyword_coverage` is between 0 and 1; low-fit candidates are not made to look high-fit through keyword stuffing.
- Resume PDFs open successfully, have no clipped/overlapping text, and remain legible at 100% zoom.
- Contact details, roles, employers, and dates match the source.
- Standard produces no cover letter. Pro produces one only when explicitly requested.

## 5. Inspect the artifacts

Each completed run writes to `outputs/<run_id>/`. Start with the change summary:

```powershell
$runDir = Join-Path "outputs" $generation.run_id
$summary = Get-Content -Raw (Join-Path $runDir "change_summary.json") | ConvertFrom-Json
$summary | Select-Object profile_name, role_title, company_name,
  keyword_coverage, validation_flags
$summary.bullet_changes | Format-Table change_reason, original_text,
  revised_text, keywords_added -Wrap
```

Then visually inspect the PDF. Character estimates are useful warnings, not proof that layout is correct. Check page count, section ordering, date alignment, line wrapping, font size, whitespace balance, and whether URLs or long skill lists overflow.

## 6. Debug by last progress step

| Last step | First places to inspect | Common causes |
|---|---|---|
| `extracting_profile` | `document_ingestion_engine.py`, `candidate_profile_builder.py` | Empty text, malformed structured response, weak headings, truncated input |
| `analyzing_job` | `job_description_analyzer.py` | Posting under 50 characters, incomplete JD, malformed structured response |
| `scoring_relevance` | `relevance_ranker.py`, `evidence_extractor.py` | Missing embedding dependency/model, empty bullets, unexpected entry types |
| `tailoring_resume` | `resume_tailoring_engine.py` | Invalid LLM JSON, unsupported claims, page-budget pruning, empty variants |
| `generating_cover_letter` | `cover_letter_generator.py`, tier request | Standard/Pro mismatch, validation rejection, missing grounded alignment |
| `validating` | `quality_validator.py`, `style_rules.py`, `resume_repair.py` | Truthfulness entities, redundancy, vague prose, repair producing invalid data |
| `rendering_pdfs` | `pdf_renderer.py`, templates/CSS | Unsupported xhtml2pdf CSS, overflow, missing output directory, bad template data |

For API errors, keep the `uvicorn` terminal visible. The client intentionally receives a generic internal-error message while the server log records the traceback.

To inspect the latest database rows without modifying them:

```powershell
python -c "import sqlite3; c=sqlite3.connect('resume_tool.db'); print(*c.execute('select run_id,status,progress_step,error_message from runs order by rowid desc limit 5'), sep='\n')"
```

## 7. Reusable review prompts

These prompts are for a human/AI review pass. They reference local files but contain no applicant data themselves.

### Grounding audit

```text
Compare the applicant profile at <PROFILE_PATH>, the job description at
<JOB_PATH>, and outputs/<RUN_ID>/change_summary.json. List every revised claim
that is not directly supported by the profile. Treat numbers, technologies,
employers, credentials, seniority, ownership, scale, and outcomes as claims.
For each issue, cite the exact source line or state "no supporting source".
Do not reward keyword coverage when the evidence is absent.
```

### Extraction audit

```text
Read <PROFILE_PATH> and the extracted CandidateProfile debug output. Produce a
field-by-field diff for contact details, experiences, dates, education,
projects, skills, awards, and source_text. Flag merged roles, duplicated roles,
normalized dates, missing bullets, and any value that was inferred rather than
copied from the source.
```

### Output quality audit

```text
Review the generated resume PDF and change_summary.json for <RUN_ID>. Score
grounding, relevance, specificity, concision, verb variety, readability, and
layout from 1-5. Fail the run if any fact is invented, any source metric is
changed, content overlaps/clips, or an unsupported JD keyword is presented as
candidate experience. Give the three highest-impact fixes.
```

### Regression comparison

```text
Compare outputs from <BASELINE_RUN_ID> and <CANDIDATE_RUN_ID> using the same
profile and JD. Ignore harmless wording variation. Report only changes in
grounding, evidence density, keyword coverage, missing qualifications,
validation flags, section selection, page count, and visual defects. Mark each
change improved, regressed, or neutral and cite the relevant artifact text.
```

## 8. Record a regression

Keep the run IDs local because generated artifacts may contain PII. Put only a sanitized defect description in an issue or commit.

```text
Date/model:
Code revision:
Local profile ID / job ID:
Tier / template / cover letter:
Last successful stage:
Expected invariant:
Observed result:
Relevant validation flags:
Reproduction frequency:
Sanitized minimal reproduction:
Suspected module:
```

When a failure is deterministic, add a unit test with the smallest inline input that reproduces it. Do not promote the full local applicant or job file into the tracked test suite.
