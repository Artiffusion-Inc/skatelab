# API Recovery Implementation Plan

> **For agentic workers:** This plan is being executed inline in the current session. Parallel untracked frontend/ML work is preserved and excluded.

**Goal:** Restore the documented `/v1` API ingress path and make video-processing tasks report durable, bounded, cost-aware states without changing ML algorithms.

**Architecture:** Keep Litestar's existing `/v1` routes, Valkey task hashes, arq worker, S3 upload flow, and Vast.ai bridge. Add only the missing state/cost fields and failure guards at those existing boundaries. Make Traefik's repository configuration the deployment source of truth and synchronize it through the existing SSH deploy path with a backup, syntax check, safe reload, and public health verification.

**Tech Stack:** Python 3.11, Litestar, Pydantic, Valkey/Redis, arq, httpx, pytest, Bash, Traefik, GitHub Actions, Dokploy.

## Global Constraints

- Preserve unrelated parallel changes in `frontend/src/components/analysis/` and `ml/`; do not edit, stage, or revert them.
- Use the canonical public API prefix `/v1`; do not add guessed compatibility prefixes.
- Keep ML algorithms and the existing `process_video_remote_async` integration unchanged.
- Never represent unknown cost as `0.0`; route estimate and actual charge are nullable and remain distinct.
- Retryable GPU failures are non-terminal only while arq has attempts remaining; exhausted retries become terminal `failed` with a clear error.
- Active task state must include a heartbeat/update timestamp and stale active tasks must fail closed rather than remain pollable forever.
- Preserve auth ownership checks, S3 key ownership, queue rollback, and existing frontend response field names.
- Do not call Vast.ai or deploy production from this session without an explicit user-approved spend limit and deployment authorization; local/fake boundary tests must be non-paid.
- No production credentials or `.env` values enter the repository.
- Confirmed OpenViking execution lessons were unavailable because the lookup timed out; no unverified lesson is encoded as a constraint.

## File Map

- Modify `backend/app/task_manager.py`: task status fields, heartbeat/retry transitions, stale guard helper, nullable cost fields.
- Modify `backend/app/config.py`: bounded retry and stale-task settings with positive-value validation.
- Modify `backend/app/vastai/client.py`: retain nullable route cost estimate in `VastResult`.
- Modify `backend/app/worker.py`: use route estimate, leave actual unknown, mark retrying without terminal failure, terminalize exhausted retries, refresh heartbeat.
- Modify `backend/app/schemas.py`: expose nullable estimate/actual fields in processing status/result contracts.
- Modify `backend/app/routes/process.py`: expose task cost/error fields and terminalize stale active state before returning it.
- Add/modify focused tests under `backend/tests/` for the above behavior.
- Add `infra/dokploy/scripts/sync-traefik-config.sh`: backup, install, validate, reload, and health-check source-driven Traefik config; support dry-run/remote execution without secrets.
- Modify `.github/workflows/deploy.yml`: invoke the sync seam before Dokploy compose redeploy and verify `/v1/health`, using existing SSH secrets only.
- Add `infra/tests/test_traefik_source.py` or a focused repository test: assert `/v1` routing and documented runtime paths stay present.

## Tasks

### Task 1: Lock the backend contracts with failing tests

**Files:** `backend/tests/test_vastai_client_extended.py`, `backend/tests/test_task_manager_unit.py`, `backend/tests/worker/test_worker_tasks.py`, `backend/tests/routes/test_process.py`, and a new focused test if an existing file cannot express the behavior.

- [ ] Add a test that a Vast route cost such as `0.0125` is retained on `VastResult.cost_estimate_usd`, while no actual cost is fabricated.
- [ ] Add a task-manager test that a retryable transition writes non-terminal `retrying`, a retry message, attempt count, and heartbeat; an exhausted transition writes terminal `failed` and the original error.
- [ ] Add a stale-task test with an old `updated_at` and active status; the guard writes `failed` with a clear stale-worker error and returns the terminal state. A fresh task remains active.
- [ ] Add a worker test proving a retryable error on an attempt below the bound does not call terminal `store_error`, publishes `retrying`, and raises `arq.Retry`; an attempt at the bound calls terminal failure and does not requeue.
- [ ] Add status-route assertions for nullable `cost_estimate_usd`, nullable `cost_actual_usd`, retry/error fields, and stale active-task terminalization.
- [ ] Add a source test asserting `infra/dokploy/traefik/traefik.yml` uses `/etc/dokploy/traefik/dynamic`, `dynamic.yml` routes `api.skatelab.ru` `/v1/` to `backend-dk:8000`, and the deployment seam names the same paths.
- [ ] Run only the new tests and confirm they fail for missing behavior rather than collection or fixture errors.

### Task 2: Implement bounded task state and cost propagation

**Files:** `backend/app/config.py`, `backend/app/task_manager.py`, `backend/app/vastai/client.py`, `backend/app/worker.py`, `backend/app/schemas.py`, `backend/app/routes/process.py`.

- [ ] Add minimal settings `task_max_attempts` and `task_stale_after_seconds` with positive validators; default the retry bound to the existing arq worker policy rather than creating a second scheduler.
- [ ] Add `RETRYING` to `TaskStatus`, initialize `updated_at`, `attempt`, `cost_estimate_usd`, and `cost_actual_usd` as empty task fields, and update `updated_at` on progress, running, retrying, completion, failure, and cancellation writes.
- [ ] Add focused task-manager operations with exact semantics: `mark_retrying(task_id, message, attempt)`, `store_error(..., cost_actual_usd=None)`, and `fail_stale_task(task_id, now=None)`. Stale detection must only terminalize `pending`, `running`, or `retrying` tasks whose `updated_at` is older than the configured threshold.
- [ ] Extend `VastResult` with `cost_estimate_usd: float | None`; set it from the route response with `None` when omitted. Keep `_build_auth_data` behavior intact, because Vast auth still needs its route cost value.
- [ ] Pass the route estimate to analytics/task state, never `0.0`, and leave `cost_actual_usd` as `None` because the current bridge does not return a billable actual. Do not claim actual cost from a route estimate.
- [ ] In `process_video_task`, derive `job_try` and the configured bound. Retryable errors call `mark_retrying` and publish `retrying` only below the bound; exhausted retryable errors call `store_error` and follow the existing terminal DB/session failure path. Non-retryable errors remain terminal immediately. Preserve `arq.Retry` only for retryable attempts with budget.
- [ ] Refresh the task heartbeat at existing major progress boundaries, and run stale-task terminalization from status reads so a dead worker cannot leave an indefinitely active task.
- [ ] Add nullable cost fields to the response schema and include them in `TaskStatusResponse`; include the estimate in the terminal result only as an additive nullable field if existing clients tolerate it.
- [ ] Run the focused backend tests, then the existing task/Vast/process tests; fix only regressions caused by this change.

### Task 3: Make Traefik synchronization source-driven and rollback-safe

**Files:** `infra/dokploy/scripts/sync-traefik-config.sh`, `.github/workflows/deploy.yml`, and the source consistency test.

- [ ] Create a strict Bash script accepting `--host`, `--user`, optional `--port`, `--dry-run`, and optional health URL; reject missing required values and never echo private key/API values.
- [ ] Transfer only repository `infra/dokploy/traefik/traefik.yml` and `dynamic.yml` to a temporary remote directory, validate both with the remote Traefik binary/container if available, back up current files with a timestamp, atomically install them under `/etc/dokploy/traefik/` and `/etc/dokploy/traefik/dynamic/`, then reload/restart the documented Traefik service. On validation/install failure, retain the prior files and return nonzero.
- [ ] Verify `https://api.skatelab.ru/v1/health` after reload with a bounded poll; fail the deployment if it does not return success. Keep public health verification separate from any Vast processing call.
- [ ] Add the sync step to the production workflow before the Dokploy compose deploy, reusing `VPS_HOST`, `VPS_USER`, and `VPS_SSH_KEY`; do not add secrets or use the Dokploy API key in the script. Keep the existing compose deploy and workflow concurrency.
- [ ] Run `bash -n`, shell dry-run, source tests, actionlint if installed, and Traefik config validation if a local binary/container is available. Do not run the production workflow.

### Task 4: Exercise non-paid API boundaries and report the production blocker

**Files:** focused test harness only; no production credentials.

- [ ] Determine whether disposable local PostgreSQL/Valkey/S3-compatible services already exist; do not destroy volumes or mutate production.
- [ ] Run the backend auth -> upload init/presign/complete -> queue -> status path against local services, using `APP_SKIP_AUTH=true` only for local testing and documenting any mocked S3/queue boundary.
- [ ] Exercise the worker boundary with a controlled fake `process_video_remote_async` response and the real task-state/result serialization; do not call `run.vast.ai`.
- [ ] Record timing for auth, upload, queue, worker, result, and state transitions; record cost estimate if supplied by the fake route and actual as unknown.
- [ ] Probe production health only; if the ingress remains 404 or production credentials/spend approval are unavailable, report that as the exact blocker and do not initiate processing.

### Task 5: Validate and commit only the recovery changes

- [ ] Run focused pytest, `uv run ruff check` on touched backend files, `uv run basedpyright --level error backend/app` or the narrow supported equivalent, shell/YAML/source checks, and any available local service E2E.
- [ ] Review `git diff` and `git status` to ensure the parallel ML/frontend files are neither reverted nor staged.
- [ ] Commit only the API/deployment recovery files with a conventional message, then report commit id, test commands/results, local/production status, and cost semantics.
