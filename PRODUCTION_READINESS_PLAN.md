# ApplyEasy — Indie Production Readiness Plan

**Purpose:** implementation plan and operating instructions for the agent that
takes ApplyEasy from a local prototype to a production service.

**Scope:** deployment, reliability, security, privacy, cost control, and
operations. Product-quality work remains in `ROADMAP.md`; do not duplicate it
here. When the two plans overlap, complete the production prerequisite here and
leave feature sequencing to the product roadmap.

**Guiding decision:** ship a controlled single-instance beta first, then add
distributed infrastructure only when public access or measured load requires
it. Do not build a microservice fleet for an indie product.

---

## 1. Definition of done

ApplyEasy is production-ready when all of the following are true:

- A push to the release branch runs tests and produces reproducible frontend
  and backend builds.
- The app is available over HTTPS at one origin; `/api` routes to FastAPI.
- Generation continues independently of the browser and has a hard deadline.
- A process restart cannot leave a run permanently stuck in `running`.
- Resume/JD data and generated documents are private, expire automatically,
  and can be deleted.
- Pro/paid functionality is authorized by the server, never trusted from the
  request body.
- Abuse and provider spend have hard limits.
- Operators can determine whether the API, generation pipeline, database, and
  storage are healthy without reading raw user content.
- Backup/restore and rollback procedures have been tested once.

“The homepage loads” or “Uvicorn is running” is not sufficient.

---

## 2. Target architecture

### Stage 1 — controlled beta

Use this for an invite-only or tightly rate-limited launch:

1. Static Vite build served by a CDN or reverse proxy.
2. One always-on application container running one FastAPI process.
3. Same-origin routing: `https://<domain>/api/*` proxies to FastAPI.
4. SQLite and generated files on one encrypted persistent volume.
5. A bounded in-process job executor, run deadline, and startup reconciliation.
6. Managed secrets, HTTPS, logs, alerts, backups, retention cleanup, and strict
   global/user/IP quotas.

This is intentionally a **single-instance system**. Do not add API replicas or
multiple Uvicorn workers while SQLite, local artifacts, and in-memory limits are
in use. A deploy may interrupt an active job; reconciliation must make that
failure explicit and retryable.

### Stage 2 — public production

Move here before unrestricted signup, horizontal scaling, or meaningful paid
traffic:

1. Stateless FastAPI service.
2. PostgreSQL for users, sessions, runs, and artifact metadata.
3. Redis-backed durable queue and one or more generation workers.
4. Private S3-compatible object storage for PDFs and summaries.
5. Distributed rate limits, server-side entitlements, retries, idempotency, and
   queue monitoring.

Keep the API and worker in the same codebase and container image. They are two
process roles, not two independently designed products.

### Promotion triggers

Promote from Stage 1 to Stage 2 when any one is true:

- public/anonymous access is opened;
- paid plans are enabled;
- more than one API instance or worker is needed;
- deploy interruptions become material;
- SQLite locking, queueing delay, or disk management causes incidents;
- sustained generation concurrency exceeds the tested Stage 1 limit.

---

## 3. Execution order

The future agent should work phase by phase. Keep the application usable at the
end of every phase, add tests with each behavior change, and update this file’s
checkboxes and decision log as work lands.

## Phase 0 — baseline and decisions

**Goal:** remove ambiguity before changing infrastructure.

- [ ] Record a clean baseline: backend tests, frontend typecheck/build, one
  local end-to-end generation, typical/95th-percentile runtime, peak memory,
  output size, and Groq calls/tokens per Standard and Pro run.
- [ ] Resolve the repository/package-root mismatch. A fresh checkout must have
  one documented root from which installation, tests, and Uvicorn work.
- [ ] Fix Python packaging so the backend installs real packages; add a locked,
  reproducible production dependency set.
- [ ] Add the missing ESLint configuration or remove the nonfunctional script;
  CI must not advertise checks it cannot run.
- [ ] Decide the Stage 1 host, primary region, domain, email/contact address,
  backup location, retention duration, and monthly Groq/infrastructure budgets.
- [ ] Check whether the repository has ever been public. Complete the PII git
  history purge in `ROADMAP.md` D1 before deployment or collaboration expands.
- [ ] Inventory every environment variable. Fail startup with a clear message
  when required values are missing; never print secret values.

**Gate:** a fresh environment can install, test, build, and start the app using
only committed instructions plus injected secrets.

## Phase 1 — reproducible deployment

**Goal:** one-command/container deployment with same-origin HTTPS.

- [ ] Add a production backend container build using Python 3.11+ and a
  non-root runtime user. Pin the base image by an intentional version.
- [ ] Install and verify all PDF/rendering dependencies in the image.
- [ ] Download/cache `all-MiniLM-L6-v2` during image build or a controlled
  release step. Production must not depend on a first-user runtime download.
- [ ] Add a frontend production build and immutable static asset caching.
- [ ] Route `/api` to FastAPI at the same origin as the frontend. Keep the
  frontend’s relative `/api` client unless there is a proven need for separate
  origins.
- [ ] Add configuration for environment, public origin, trusted proxies,
  database/output locations, retention, limits, logging level, and release ID.
- [ ] Replace localhost-only CORS with exact configuration. If same-origin is
  used, do not introduce broad wildcard CORS.
- [ ] Set cookies `HttpOnly`, `Secure`, and with the correct `SameSite` policy in
  production. Avoid cross-site cookies unless necessary.
- [ ] Add liveness (`process is alive`) and readiness (`required local/shared
  dependencies are usable`) endpoints.
- [ ] Add graceful shutdown: stop accepting new generation work and bound the
  wait for active work.

**Gate:** a clean container deployment serves the complete flow over HTTPS,
survives a normal restart, and performs no runtime package/model downloads.

## Phase 2 — reliable beta jobs

**Goal:** make the current automatic backend execution bounded and honest.

- [ ] Put a pipeline-level wall-clock deadline around the entire run, in
  addition to existing per-Groq-call timeouts.
- [ ] Add explicit attempt count, started/heartbeat timestamps, terminal reason,
  and pipeline/release version to each run.
- [ ] On startup, reconcile stale `pending`/`running` records to a documented
  terminal state. Never leave the UI polling forever.
- [ ] Enforce a small global concurrency limit. Queue excess beta work or return
  a clear `429/503` with `Retry-After`; do not allow unbounded thread creation.
- [ ] Make completion idempotent: a retry must not corrupt state or expose one
  user’s artifacts to another.
- [ ] Define which failures may retry. Do not blindly retry invalid inputs or
  repeatedly charge for deterministic LLM parse failures.
- [ ] Persist a user-safe failure code separately from internal diagnostic
  details. Never return tracebacks, prompts, resume text, or provider responses.
- [ ] Add integration tests for success, timeout, provider failure, restart
  reconciliation, duplicate execution, and download authorization.

**Gate:** forced timeout, simulated Groq failure, and process restart all result
in an accurate, user-visible terminal state with no cross-user access.

## Phase 3 — privacy and security

**Goal:** safely handle resumes as sensitive personal information.

- [ ] Document what is collected, why it is sent to Groq, how long it is kept,
  and how a user requests deletion. Publish privacy policy and terms before
  accepting public data.
- [ ] Verify Groq’s current retention/training/contract terms for the intended
  customer type and region. Record the decision; do not assume.
- [ ] Add automatic deletion of raw resumes, JDs, run rows, PDFs, and summaries
  after the chosen retention window. Cleanup must be observable and retryable.
- [ ] Add a user-facing deletion path. Deleting metadata and artifacts should
  be one idempotent operation.
- [ ] Redact user content, cookies, authorization headers, prompts, and provider
  payloads from logs and error tracking.
- [ ] Validate PDF signature/type, page count, extracted-text size, and parsing
  time as well as byte size. Reject unsupported files with safe messages.
- [ ] Run parsing/rendering with resource limits. Treat every upload as
  untrusted input.
- [ ] Replace “legacy ownerless records are public” behavior before launch.
- [ ] Add CSRF protection if cookie-authenticated state-changing endpoints can
  be reached cross-site. Configure proxy headers only from known proxies.
- [ ] Enable security headers: HSTS, CSP appropriate to the frontend, MIME
  sniffing protection, frame restrictions, and a conservative referrer policy.
- [ ] Run dependency and secret scanning in CI; define a patching cadence.

**Gate:** a test user can create and delete a run, another browser cannot read
it, expired artifacts disappear, and logs contain no resume/JD content.

## Phase 4 — identity, entitlements, and cost controls

**Goal:** prevent anonymous abuse and uncontrolled AI spending.

- [ ] Choose one indie-appropriate access model: invite codes for beta, or a
  managed authentication provider for public accounts. Do not build custom
  password storage.
- [ ] Bind sessions/runs to a server-verified principal. The owner cookie may
  remain as a guest mechanism but is not a paid entitlement.
- [ ] Never trust `tier`, cover-letter access, model choice, or generation quota
  from the client. Resolve them server-side from the user/account.
- [ ] Add per-user and per-IP limits plus a global concurrency and daily-spend
  circuit breaker. Use a trusted proxy-derived client address.
- [ ] Add idempotency keys to generation requests so retries/double-clicks do
  not create duplicate paid runs.
- [ ] Track per-run provider/model, call count, latency, token usage when
  available, estimated cost, and failure class—without storing prompt content.
- [ ] Configure Groq quota/spend alerts and an application-side hard ceiling.
- [ ] If public anonymous generation remains, add bot protection and a much
  lower anonymous quota.

**Gate:** direct API calls cannot self-upgrade to Pro, duplicate submission is
charged once, and exhausting a budget fails safely without destabilizing API
reads/downloads.

## Phase 5 — CI/CD and operations

**Goal:** make releases routine and incidents diagnosable.

- [ ] CI: backend unit/integration tests, real PDF smoke test, frontend
  typecheck/build/lint, dependency scan, secret scan, and container build.
- [ ] CD: deploy to staging, run smoke tests, migrate safely, deploy production,
  verify health, and support rollback to the previous image.
- [ ] Use structured logs with `request_id`, `run_id`, stage, duration, status,
  and release ID. Hash or omit user identifiers.
- [ ] Add error tracking and metrics for request errors, generation success,
  stage latency, queue/concurrency, stale runs, Groq errors, PDF errors, cleanup,
  storage, and cost.
- [ ] Alert only on actionable conditions: service unavailable, failure-rate
  spike, stale jobs, budget threshold, low disk, failed backup/cleanup.
- [ ] Back up the Stage 1 persistent volume; test a restore. For Stage 2, use
  managed PostgreSQL backups and object-storage lifecycle/versioning as needed.
- [ ] Write a short runbook covering provider outage, stuck jobs, disk full,
  leaked key, bad deploy, database restore, and user deletion request.
- [ ] Run a small load test using synthetic resumes. Establish supported
  concurrency and reject excess load predictably.

**Gate:** a deliberately bad release can be rolled back, a backup can be
restored, and a simulated stuck-job/provider incident triggers the expected
alert and runbook.

## Phase 6 — Stage 2 migration (defer until triggered)

**Goal:** introduce shared durability without redesigning the product.

- [ ] Change storage configuration from `DB_PATH` to a general `DATABASE_URL`.
- [ ] Add Alembic migrations and migrate SQLite data to managed PostgreSQL.
- [ ] Introduce Redis and a durable job library. API writes the run and enqueues
  only a run ID; the worker reads source data from shared storage.
- [ ] Store artifacts in private object storage. Keep object keys, checksums,
  sizes, content types, expiry, and status in PostgreSQL.
- [ ] Serve downloads through short-lived signed URLs or an authorized API
  redirect. Never make the bucket public.
- [ ] Move rate limits and idempotency state to Redis/PostgreSQL.
- [ ] Make worker retries use exponential backoff with a small maximum attempt
  count and a dead-letter/failed state visible to operators.
- [ ] Deploy API and worker from the same image with distinct commands. Scale
  workers from queue/load evidence, not guesswork.
- [ ] Perform a staged migration with backups, reconciliation counts, artifact
  checks, and an explicit rollback window.

**Gate:** an API restart or worker restart does not lose a queued job, and two
API instances return consistent status/download authorization.

---

## 4. Environment contract

Use names similar to the following; the exact naming may change once, early.
Document every live variable in `.env.example` without real values.

**Required in all deployed environments**

- `APP_ENV`, `RELEASE_ID`, `PUBLIC_ORIGIN`
- `GROQ_API_KEY`
- `DATABASE_URL` (or Stage 1 `DB_PATH` during the temporary beta)
- `ARTIFACT_STORAGE_BACKEND`, plus Stage 1 output path or Stage 2 bucket values
- `RETENTION_DAYS`
- `PIPELINE_DEADLINE_SECONDS`, `MAX_CONCURRENT_RUNS`
- rate/quota/budget settings
- trusted proxy and allowed-origin settings

**Stage 2 additions**

- `REDIS_URL`
- object-storage endpoint/region/bucket and workload identity/credentials
- worker concurrency and retry settings

Secrets belong in the hosting provider’s secret manager. Local `.env` files are
for development only. Rotate any key that may have entered logs or git history.

---

## 5. Required test matrix

Keep the matrix small but meaningful:

| Layer | Minimum coverage |
|---|---|
| Unit | parsing, ownership, limits, state transitions, cleanup, entitlement |
| Integration | DB + job execution + storage using mocked Groq |
| Rendering | one sparse, typical, and oversized resume through the active renderer |
| End to end | upload → generate → poll → authorized download → delete |
| Failure | timeout, provider 429/5xx, malformed provider output, restart, disk/storage failure |
| Security | cross-user access, tier escalation, CSRF policy, unsafe upload limits |
| Deployment | container starts cold with network-independent model/runtime assets |

Use synthetic fixtures only. Never place real resumes, JDs, PDFs, prompts, or
production database snapshots in git or CI artifacts.

---

## 6. Release gates

### Private beta may launch when

- Phases 0–3 and Phase 5 are complete.
- Access is invite-only or strongly limited.
- Stage 1 single-instance constraints are documented and enforced.
- Server-side Pro access and global spend/concurrency ceilings exist, even if
  billing does not.
- Restore, rollback, retention cleanup, and deletion have each been exercised.

### Public production may launch when

- Phase 4 is complete.
- Stage 2 is complete unless measured evidence demonstrates that the public
  launch remains safely within the controlled single-instance envelope.
- Privacy/terms and provider data-use decisions are published.
- Load and failure tests meet the service targets chosen below.

Suggested initial targets for an indie launch:

- API availability target: 99.5% monthly.
- Status/download p95 latency: under 500 ms, excluding artifact transfer.
- Successful generation rate: at least 95%, excluding rejected user input.
- Standard generation p95: under 90 seconds; hard deadline no more than 180
  seconds unless measurements justify a different value.
- Zero permanently stuck runs; zero cross-user artifact disclosures.

These are starting targets, not promises to customers. Revise them from data.

---

## 7. Explicit non-goals for the first launch

- Kubernetes, service mesh, or separately versioned microservices.
- Multi-region active-active infrastructure.
- A custom identity/password system.
- Custom billing before product access and entitlements are secure.
- Unlimited anonymous generation.
- Building every Pro roadmap feature before validating the core paid workflow.
- Storing raw LLM prompts/responses “for analytics.”

Prefer managed PostgreSQL/Redis/object storage/auth when Stage 2 is reached.
The goal is a boring system that one developer can operate.

---

## 8. Instructions for the implementing agent

1. Read `README.md`, `CLAUDE.md`, `ROADMAP.md`, `AUDIT_REPORT.md`, and this file
   before changing architecture.
2. Inspect the current worktree and preserve unrelated user changes.
3. Start each phase by recording assumptions and an acceptance-test plan.
4. Make the smallest vertical slice that satisfies the phase gate; avoid
   speculative abstractions.
5. Keep API responses backward-compatible unless a migration is explicitly
   planned. Version persisted job payloads before a queue is introduced.
6. Treat privacy, authorization, quota, and deletion tests as release blockers.
7. Never run a destructive migration or history rewrite without a verified
   backup, exact target review, and explicit user approval where required.
8. Do not deploy, purchase services, change DNS, enable billing, send messages,
   or alter external accounts without the user’s authorization.
9. After each phase, update checkboxes, environment documentation, runbooks,
   and the decision log. Report commands/tests actually run and unresolved risk.
10. Stop at the Stage 1/Stage 2 boundary unless a promotion trigger is met or
    the user explicitly requests Stage 2. This is the main indie-scope guardrail.

---

## 9. Decision log

Record durable decisions here so future agents do not repeatedly reopen them.

| Date | Decision | Reason | Revisit trigger |
|---|---|---|---|
| 2026-08-25 | Same-origin frontend and API | Simplifies cookies, CORS, downloads, and operations | A real separate-origin requirement |
| 2026-08-25 | Controlled single-instance beta before distributed stack | Fastest responsible indie launch | Any Stage 2 promotion trigger |
| 2026-08-25 | API and worker share code/image in Stage 2 | Avoid premature microservices | Independent release/scaling needs backed by evidence |
| 2026-08-25 | PostgreSQL + Redis queue + private object storage for public scale | Durable shared state and restart safety | Major platform constraint |

