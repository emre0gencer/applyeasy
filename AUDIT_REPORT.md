# ApplyEasy — Consolidated End-to-End Audit

**Date:** 2026-06-26
**Scope:** 5 parallel sub-agents covering Architecture, Security, Performance, Tech Debt, Maintainability. Read-only audit — cross-cutting issues (flagged by multiple agents) are noted and weighted up.

**Status legend:** ☐ open · ☑ fixed

---

## 🔴 P0 — Critical (fix before any deployment / sharing)  — ✅ ALL FIXED 2026-06-26

**1. ☑ User-resume PII is committed to git** *(Security · Maintainability)*
**FIXED:** `.gitignore` now root-anchors `/outputs/`, `/test_profiles/`, `/test_jobs/`; ran `git rm -r --cached` on all three (183 files untracked). ⚠️ History purge still required if this repo was ever pushed/shared — not done here.
`.gitignore:19` ignores `backend/outputs/`, but the renderer writes to `outputs/` at **repo root** (`pdf_renderer.py:54`). Result: **139 tracked files** with real names, employers, and full resume content in `change_summary.json` + `resume.pdf`. Durable in history.
→ `git rm -r --cached outputs/ test_profiles/ test_jobs/`; change `.gitignore` to root-anchored `/outputs/`; purge history if ever pushed.

**2. ☑ No timeout/retry on any Groq LLM call → runs hang forever** *(Performance, also Arch #3/#4)*
**FIXED:** all four `_get_client()` constructors now use `Groq(api_key=..., timeout=30.0, max_retries=2)` (`resume_tailoring_engine.py`, `job_description_analyzer.py`, `candidate_profile_builder.py`, `cover_letter_generator.py`). Each call now hard-fails instead of hanging. *Follow-up (P1):* add an overall pipeline-level deadline that marks the run `failed`.

**3. ☑ Frontend polls indefinitely, swallowing all errors** *(Arch + Performance — flagged twice)*
**FIXED:** `GeneratingStep.tsx` poll loop now enforces a 3-minute wall-clock limit and aborts after 5 consecutive fetch errors, calling `onFailed()` with a user-facing message in both cases. Backend death/404 can no longer strand the user.

---

## 🟠 P1 — High (correctness, abuse, blockers)  — ✅ ALL FIXED 2026-06-26

**4. ☑ No auth + IDOR on `/status` & `/download`** *(Security)*
**FIXED via per-browser ownership binding** (chosen over full auth). New `backend/src/api/ownership.py` mints an opaque owner token into an HttpOnly cookie on `/upload`; `sessions` + `runs` gained an `owner_id` column (idempotent migration verified on a legacy DB). `/generate` verifies the caller owns the session and propagates the owner to the run; `/status` + all `/download` routes return 404 unless the caller's cookie matches the run's owner. Frontend `client.ts` now sends `credentials: "include"`. Legacy records (`owner_id IS NULL`) stay accessible for back-compat. **Verified end-to-end:** owner reads 200, stranger blocked 404 on status & download. ⚠️ *Prod note:* cross-origin deploys need `SameSite=None; Secure` on the cookie + pinned CORS origins (see #21).

**5. ☑ No rate limiting on expensive endpoints** *(Security)*
**FIXED:** added `backend/src/api/rate_limit.py` — a per-process, per-IP sliding-window limiter (no new deps). `/generate` capped at 10/min, `/upload` at 20/min, both wired as route dependencies; returns 429 + `Retry-After`. Verified trips at the 3rd over-limit call.

**6. ☑ Backend run command is wrong — fails on clean checkout** *(Maintainability)*
**FIXED:** README + CLAUDE.md now instruct installing from `backend/` then running uvicorn/pytest **from repo root** (with an explicit note on why, and the `ModuleNotFoundError` symptom). Packaging restructure (moving `pyproject.toml` to root) left as an optional follow-up — running from root works via implicit namespace packages, and all 49 tests pass that way.

**7. ☑ Full Python tracebacks returned to the browser** *(flagged by 3 agents)*
**FIXED:** `orchestrator.py` now `logger.exception(...)` server-side and stores a generic `"Generation failed due to an internal error. Please try again."` in `error_message`. `/status` relays only that. Removed the now-dead `traceback`/`json` imports.

**8. ☑ PDF one-page-fit loop renders up to 8× per resume** *(Performance H2)*
**FIXED:** `render_resume_pdf` now renders once at full size (fast path for most resumes) and otherwise **binary-searches** the largest fitting scale (≤5 renders total vs up to 8 linear), always falling back to the 72% floor. Behaviour preserved; 49 tests green.

**9. ☑ No input-size caps → context-window blowouts** *(Performance H4)*
**FIXED:** `/upload` caps stored profile text at 60k chars; `/generate` rejects job descriptions >20k chars (422); `orchestrator._execute_pipeline` defensively truncates `raw_text`/`jd_text` regardless of entry path.

**10. ☑ SQLite locking under concurrency** *(Performance H5)*
**FIXED:** `database.py` engine now uses `timeout=30` and a `connect` event listener setting `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=30000`, so the status poller can read while a run writes. Verified `journal_mode=wal`. Added `*.db-wal`/`*.db-shm` to `.gitignore`. (Batching the ~6 progress commits/run left as optional follow-up.)

---

## 🟡 P2 — Medium (robustness, dead features, drift)

**11. Cover-letter subsystem fully built but permanently dead** *(flagged by 3 agents)*
`JobDescriptionStep.tsx:143` hardcodes `false`; entire `cover_letter_generator.py`, `render_cover_letter_pdf`, `/download/.../cover-letter`, and threaded `includeCoverLetter` prop are unreachable. **The documented `COVER_LETTER_ENABLED = False` gate does not exist** — doc drift. → Wire one real feature flag or delete the subsystem.

**12. PDF upload path unreachable from UI** *(Arch #2)* — backend + `uploadFile()` support multipart PDF/.txt, but no file input exists; only `uploadText` is wired.

**13. Invalid LLM JSON degrades silently to blank resume** *(Perf M9)* — every parse falls back to empty/original with no flag; a `{}` extraction "completes" successfully. → Detect empty critical extractions and fail/flag; retry once.

**14. Blocking sync work inside `async` handlers** *(Perf M6)* — `upload.py:20` runs pdfplumber parsing + sync commits in the event loop. → make `def` or `run_in_threadpool`.

**15. Embeddings encoded per-entry, not batched** *(Perf H3)* — `relevance_ranker.py:69-77` calls `encode` 5–15×/run. → one batched `encode`.

**16. Embedding model cold-loads on first request** *(Perf M8)* — warm in `lifespan` startup instead of inside a user's background task.

**17. Background-task crash orphans runs** *(Arch #4)* — no startup reconciliation; killed worker leaves `running` forever. → watchdog/TTL sweep.

**18. Missing `.env.example` + stale README/CLAUDE.md** *(Maintainability)* — no secret template; `load_dotenv` hard-coded to `backend/.env`; CLAUDE.md falsely claims outputs are untracked and references nonexistent `ANTHROPIC_API_KEY` note. → add `backend/.env.example`, reconcile docs.

**19. No CI; no Python lockfile** *(Maintainability)* — `pytest`/`tsc`/`lint` exist but nothing runs them; `>=` floors only → non-reproducible installs. Doc/command drift goes undetected.

**20. Duplicated headline-score logic frontend↔backend** *(Tech Debt TD-6)* — `scoreUtils.ts:13` reimplements suitability with **different weights** than `quality_validator.compute_raw_suitability_v2`; already documented to have diverged once. → single source of truth server-side.

**21. CORS dev-only, no prod origin env** *(Arch #7 / Security)* — `main.py:33-43` hardcodes localhost; `allow_credentials=True` + wildcard methods is risky if origins broaden.

---

## 🟢 P3 — Low (cleanup, polish)

- **Dead code:** `ProfileStep.tsx` (unimported), `client.ts:43 uploadFile`, orchestrator unused imports (`json`, `Optional`, `get_run_record`), v1 `compute_raw_suitability`, `centerDivider` no-op, duplicate `_req_matched`/`_req_matched_pref`. *(Tech Debt)*
- **Magic-number drift:** page-capacity constants differ across 3 modules (3600 / 3200 / 380). *(TD-4)*
- **Duplication:** prohibited-phrase lists (TD-5), "glass card" inline styles across 3 components (LD-2), two near-identical PDF helpers (LD-3). → extract shared modules.
- **`ValidationResult` v2 fields computed but never persisted/surfaced** (TD H-2) — 4 evidence checks run, only `flags` saved.
- **No artifact/DB cleanup** (Perf L11) — unbounded `outputs/` + DB growth.
- **No frontend tests at all**; backend tests skip API/orchestrator/pdf/db layers.
- **Naming drift:** "ApplyEasy" vs `resume-tailor-*` package names, `resume_tool.db`, FastAPI title.
- **Prompt injection** (self-scoped, low risk — output HTML-escaped); **unpinned deps + untrusted PDF parsing** (pdfplumber/PyMuPDF CVE surface).
- **Client state not persisted** — refresh drops an in-flight/finished run (Arch #6).

---

## Cross-cutting themes
1. **The "stuck forever" failure mode** (#2+#3+#7+#17) is the highest-impact reliability gap — a single LLM hiccup strands the user with a stack trace and no recovery.
2. **PII + no-auth + no-rate-limit** (#1+#4+#5) together make the app unsafe to deploy as-is.
3. **Doc/packaging drift** (#6+#11+#18) means a new dev cannot follow the README to a running app, and CLAUDE.md contains at least 3 false statements.

**Suggested first sprint:** #1 (PII), #2+#3+#7 (failure handling), #6 (run command/packaging) — these unblock safe deployment and onboarding with relatively small diffs.
