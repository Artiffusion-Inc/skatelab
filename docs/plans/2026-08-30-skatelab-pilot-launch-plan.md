# SkateLab Pilot Launch Implementation Plan

> **For agentic workers:** After this plan is written, present the execution gate to the user (`/goal-prep` board vs inline executing-plans). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reliable video-first pilot for 5-20 coaches and athletes using Android athlete capture and web coach review.

**Architecture:** Preserve existing backend/KMP/Android/frontend boundaries. Close the product as vertical slices, not layer-by-layer: auth and relationship, upload and processing, result and feedback, then release operations. Keep all long-running work restart-safe and all sensor data explicitly unavailable or unvalidated unless real hardware evidence exists.

**Tech Stack:** Litestar, SQLAlchemy, Alembic, PostgreSQL, S3/RustFS, Valkey/arq, Vast.ai GPU worker, Python 3.11, pytest, Ruff, basedpyright, Kotlin Multiplatform, Ktor, Android Compose, CameraX, BLE adapters, Room, WorkManager, Hilt, Next.js 16, React 19, TanStack Query, Vitest, Biome, Bun.

## Global Constraints

- Work directly on `master`; do not create branches or worktrees.
- Preserve unrelated dirty changes; never reset, checkout, clean, stash, or rewrite user work.
- Commit every validated deliverable and push to `origin/master`.
- Pilot scope is coaches plus athletes, 5-20 users, Android athlete client and web coach console.
- Video-first pilot; WT901/EdgeSense is optional and all sensor output remains `synthetic/unvalidated` until hardware acceptance.
- No public accuracy claims, paid billing, iOS release, new ML models, or broad element expansion.
- Keep `mobile/shared/src/commonMain` free of Android/iOS APIs.
- Use existing dependencies; do not add a dependency for work covered by current libraries or stdlib.
- Do not run Valkey locally; use mocks, unit tests, or already available production smoke endpoints.
- Use `uv` for Python, `bun` for frontend, and `./gradlew --no-daemon --max-workers=1` for mobile.
- Never print or commit credentials, tokens, passwords, keystores, signed URLs, production `.env`, raw videos, IMU payloads, or private user data.
- Every non-trivial behavior gets one focused regression test before production code.
- Never claim a test/build is hardware validation or coach-validity evidence.

## Current Source Of Truth

- Product intent: `PRODUCT.md`.
- Approved design: `docs/specs/2026-08-30-skatelab-pilot-launch-design.md`.
- Existing mobile scope: `docs/plans/2026-08-29-skatelab-android-mvp-plan.md`.
- Existing UI inventory: `docs/specs/2026-08-29-skatelab-mobile-ui-reproduction.md`.
- Current API route inventory: `backend/app/routes/`.
- Current KMP APIs: `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/`.
- Current production health check: `https://api.skatelab.ru/v1/health`.

## Execution Lessons

- Gradle is memory-sensitive on this machine: use `--no-daemon --max-workers=1` and preserve current Gradle memory settings.
- Concurrent edits can appear in shared mobile files; inspect `git status` before every commit and preserve unrelated changes.
- `:shared:allTests` may report `NO-SOURCE` while Android unit tests still execute common tests; use `:shared:testDebugUnitTest` for explicit evidence.
- Do not start local Valkey for normal development; isolate Valkey-dependent backend tests.
- Production release signing files stay outside the repository; CI consumes environment secrets only.

## File Map

### Backend contracts and business events

- Modify `backend/app/schemas.py` — exact request/response fields and nullable auto-detection click.
- Modify `backend/app/routes/auth.py`, `backend/app/routes/sessions.py`, `backend/app/routes/process.py`, `backend/app/routes/uploads.py` — contract and ownership fixes only.
- Modify `backend/app/routes/connections.py`, `backend/app/routes/training_plans.py`, `backend/app/routes/notifications.py`, `backend/app/routes/choreography.py`, `backend/app/routes/users.py` — pilot contract consistency.
- Modify `backend/app/worker.py` — terminal events and notification producer calls.
- Create or modify `backend/app/services/notification_events.py` — one small event-to-notification mapping layer if existing helpers cannot cover producers.
- Modify `backend/app/crud/notifications.py`, `backend/app/models/notifications.py` — idempotency and payload constraints.
- Modify `backend/tests/routes/`, `backend/tests/services/`, `backend/tests/test_task_manager.py` — focused contract and ownership tests.

### KMP shared product logic

- Modify `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/SkateLabClient.kt` — expose all pilot APIs.
- Modify `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt`, `ProcessApi.kt`, `SessionsApi.kt`, `UploadsApi.kt` — exact wire contracts.
- Modify `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/state/` — shared state machines and recovery.
- Keep new API models in `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/models/`.
- Add MockEngine tests in matching `mobile/shared/src/commonTest/kotlin/`.

### Android athlete client

- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt` — durable upload/process workflow.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/` — only required migration/state fields.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/`, `ui/processing/`, `ui/session/`, `navigation/` — pilot states and routes.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/di/` — wire shared APIs and workers.
- Add/modify tests under `mobile/androidApp/src/test/` and `src/androidTest/` where available.

### Web coach console

- Modify `frontend/src/lib/api-client.ts` and `frontend/src/lib/api/` — typed API hooks and cache invalidation.
- Modify `frontend/src/app/(app)/sessions/`, `upload/`, dashboard routes — coach review and invite flows.
- Add tests under `frontend/src/lib/api/__tests__/` and route/component tests.
- Use existing design system and Russian-first strings; do not create a second UI system.

### Release and evidence

- Modify `.github/workflows/ci.yml`, `.github/workflows/android-release.yml` only when checks or artifact provenance require it.
- Create `docs/runbooks/pilot-operations.md` — support, rollback, deletion, stuck-job recovery.
- Create `docs/runbooks/production-smoke.md` — safe authenticated smoke procedure without secrets in logs.
- Create `docs/verification/2026-08-30-pilot-readiness.md` — commands, evidence, known limitations, and explicit hardware deferral.
- Create `docs/verification/2026-08-30-pilot-e2e.md` — dated synthetic and production-safe smoke evidence.

## Delivery Order

Execute tasks in order. Tasks 1-4 are blocking contracts. Tasks 5-9 produce the usable pilot. Tasks 10-14 harden and release it.

### Task 1: Freeze Pilot Contract And Test Inventory

**Deliverable:** one authoritative endpoint/state matrix prevents implementation drift.

**Files:** `docs/specs/2026-08-30-skatelab-pilot-launch-design.md`, `docs/verification/2026-08-30-pilot-readiness.md`, new `backend/tests/contracts/test_pilot_contract_inventory.py` if useful.

- [ ] Step 1: Enumerate every pilot operation from the approved design and map it to one backend route, one shared API method, one client state, and one acceptance test.
- [ ] Step 2: Mark each route as `covered`, `missing`, `mismatched`, or `blocked by infrastructure`; do not hide errors under broad TODO lists.
- [ ] Step 3: Add contract assertions for the two known historical failures:

```python
def test_reset_password_wire_name_is_password():
    assert ResetPasswordRequest(token="t", password="password123").model_dump() == {
        "token": "t",
        "password": "password123",
    }


def test_process_person_click_is_optional_for_auto_detection():
    assert ProcessRequest(video_key="uploads/video.mp4").person_click is None
```

- [ ] Step 4: Run:

```bash
uv run pytest backend/tests/contracts -q --import-mode=importlib --no-cov
```

Expected: contract inventory is executable and failures identify exact missing behavior.
- [ ] Step 5: Commit:

```bash
git add docs/specs docs/verification backend/tests/contracts
git commit -m "docs(pilot): freeze launch contract inventory"
git push origin master
```

### Task 2: Close Auth, Profile, And Session Ownership

**Deliverable:** coach and athlete can authenticate, recover account, complete profile basics, and never access another user's data.

**Files:** `backend/app/routes/auth.py`, `backend/app/routes/users.py`, `backend/app/routes/sessions.py`, `backend/app/schemas.py`, `backend/tests/routes/test_auth.py`, `backend/tests/routes/test_users.py`, `backend/tests/routes/test_sessions.py`, `mobile/shared/src/commonMain/kotlin/ru/skatelab/shared/api/AuthApi.kt`, `UsersApi.kt`, `mobile/shared/src/commonTest/`, `frontend/src/lib/api/`.

- [ ] Step 1: Add RED tests for reset payload `password`, expired/invalid token, refresh rotation, logout, profile update, and cross-user session access.
- [ ] Step 2: Run focused backend and shared tests; verify failures are contract failures, not missing services.
- [ ] Step 3: Implement exact schemas and map backend errors to `AppError.Auth`, `Conflict`, `Validation`, or `Server`.
- [ ] Step 4: Add tests for empty/invalid fields and safe error bodies; assert no password/token appears in logs or response details.
- [ ] Step 5: Run:

```bash
uv run pytest backend/tests/routes/test_auth.py backend/tests/routes/test_users.py backend/tests/routes/test_sessions.py -q --import-mode=importlib --no-cov
cd mobile && ./gradlew :shared:testDebugUnitTest --no-daemon --max-workers=1
cd ../frontend && bun test
```

- [ ] Step 6: Commit `feat(pilot): close auth profile and ownership contracts`.

### Task 3: Close Coach-Athlete Connections

**Deliverable:** controlled coach onboarding works end to end.

**Files:** `backend/app/routes/connections.py`, connection CRUD/models/schemas, `backend/tests/routes/test_connections.py`, `mobile/shared/.../ConnectionsApi.kt`, `ConnectionsViewModel.kt`, `frontend/src/lib/api/connections.ts`, coach invite UI route.

- [ ] Step 1: Add RED tests for invite, pending list, accept, end, duplicate invite, expired/unknown invite, and IDOR.
- [ ] Step 2: Define one canonical connection status model shared by backend/KMP/frontend.
- [ ] Step 3: Implement idempotent invite behavior and ownership checks before mutation.
- [ ] Step 4: Invalidate coach/athlete session caches after accept/end.
- [ ] Step 5: Run backend, shared, and frontend focused tests.
- [ ] Step 6: Commit `feat(pilot): add coach athlete onboarding flow`.

### Task 4: Make Upload And Processing Fully Restart-Safe

**Deliverable:** video upload creates one session and one process task; network errors, app restart, cancellation, and auto-detection recover safely.

**Files:** `backend/app/schemas.py`, `backend/app/routes/process.py`, `backend/app/routes/uploads.py`, `backend/app/worker.py`, `backend/tests/routes/test_process.py`, `backend/tests/routes/test_uploads.py`, `backend/tests/test_task_manager.py`, `mobile/shared/.../ProcessApi.kt`, `ProcessingViewModel.kt`, `AnalysisWorkflowCoordinator.kt`, `mobile/androidApp/.../UploadWorker.kt`, Room DAO/entity/tests.

- [ ] Step 1: Add RED tests for queue without `person_click`, queue with integer coordinates, one queue call per workflow, persisted task ID, SSE terminal events, cancellation, retry, and app restart.
- [ ] Step 2: Run tests and capture exact failures.
- [ ] Step 3: Keep `person_click` nullable through schema, route, arq job, and Vast.ai request; use auto-detection when absent. Convert UI float coordinates to backend integer pixels only when coordinates exist.
- [ ] Step 4: Ensure `UploadWorker` persists `sessionId` and `processTaskId` before returning success; a retry after process creation must observe existing task instead of enqueueing again.
- [ ] Step 5: Make SSE stop on completed/failed/cancelled terminal payloads; retry only transient transport interruption.
- [ ] Step 6: Run:

```bash
uv run pytest backend/tests/routes/test_process.py backend/tests/routes/test_uploads.py backend/tests/test_task_manager.py -q --import-mode=importlib --no-cov
cd mobile && ./gradlew ktlintCheck :shared:testDebugUnitTest :androidApp:testDebugUnitTest --no-daemon --max-workers=1
```

- [ ] Step 7: Commit `fix(pilot): make upload processing restart safe`.

### Task 5: Close Result, Metrics, And Provenance

**Deliverable:** completed Axel/video result is understandable and honest.

**Files:** backend result/metrics/phases/scores routes and schemas, `backend/tests/routes/test_metrics.py`, `test_phases.py`, `test_scores.py`, shared result models/state, Android session detail, frontend session detail.

- [ ] Step 1: Add RED tests for completed, processing, failed, video-only, missing sensor, synthetic sensor, corrupt sensor, and unavailable metric states.
- [ ] Step 2: Verify result payload has stable IDs, status, timestamps, phases, score, recommendations, diagnostics, and provenance.
- [ ] Step 3: Implement one recommendation selection rule at state/service boundary; UI must not invent ranking.
- [ ] Step 4: Render confidence as data/model confidence, never as validated sports accuracy.
- [ ] Step 5: Run backend/shared/Android/frontend tests and a serialization round trip.
- [ ] Step 6: Commit `feat(pilot): expose honest analysis result states`.

### Task 6: Add Notification Producers And Deep-Link Contract

**Deliverable:** athlete receives useful typed notifications for analysis completion/failure, coach comment, training assignment, and export readiness.

**Files:** `backend/app/services/notification_events.py`, worker/comment/training/report call sites, notification tests, `mobile/shared/.../NotificationsApi.kt`, notification state/deep-link models, Android navigation, frontend notification API and routes.

- [ ] Step 1: Add RED tests asserting each business event creates one notification with owner, type, title/body, deep link, and typed payload.
- [ ] Step 2: Add idempotency key `(recipient, event_type, source_id)` so worker retries do not duplicate notifications.
- [ ] Step 3: Emit events only after successful transaction boundaries; failed analysis emits failure notification without claiming a result.
- [ ] Step 4: Define stale/unknown deep links as safe navigation to notifications with explanatory state.
- [ ] Step 5: Run focused tests and ownership/IDOR tests.
- [ ] Step 6: Commit `feat(pilot): connect notification business events`.

### Task 7: Coach Session Review And Comments

**Deliverable:** coach can find athlete sessions, inspect result, and send one actionable comment.

**Files:** backend comment route/model/migration if absent, session routes, frontend session list/detail/comment components, frontend tests, shared session/comment models where Android needs notifications.

- [ ] Step 1: Add RED tests for coach visibility only after accepted connection, comment ownership, empty state, pagination, and cache invalidation.
- [ ] Step 2: Keep server filters limited to supported `user_id`, `element_type`, `limit`, `cursor`; implement display-only local filters for unsupported status/date/season until backend supports them.
- [ ] Step 3: Add comment creation and notification event in one tested business operation.
- [ ] Step 4: Render loading, empty, processing, failed, completed, and unavailable-data states.
- [ ] Step 5: Run `bun test`, `bun run typecheck`, `bun run lint`, and backend focused tests.
- [ ] Step 6: Commit `feat(web): ship coach session review loop`.

### Task 8: Training Plans And Program Export Pilot Surface

**Deliverable:** coach can generate a training plan from a completed result and export a real report; choreography remains bounded to tested contracts.

**Files:** training plan routes/services/tests, choreography routes/services/tests, shared APIs/models already present, frontend program/training routes, PDF report tests.

- [ ] Step 1: Add RED tests requiring completed owned session before plan generation, idempotent generation, and safe error state.
- [ ] Step 2: Add RED tests for PDF bytes `%PDF-1.4`, `application/pdf`, content disposition, ownership, and no SVG fallback.
- [ ] Step 3: Connect report export-ready notification after successful generation only.
- [ ] Step 4: Keep music upload platform-specific; shared code exposes metadata and analysis contracts, not `File`/`NSData`.
- [ ] Step 5: Run focused backend/shared/frontend tests.
- [ ] Step 6: Commit `feat(pilot): add training and report workflows`.

### Task 9: Android Pilot UX Completion

**Deliverable:** Android athlete can complete pilot flow without dead ends.

**Files:** `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt`, `presentation/navigation/AppNavigation.kt`, auth/camera/processing/session/profile screens, resource strings, Hilt modules, tests.

- [ ] Step 1: Add state/navigation tests for login, invitation, permission denied, gallery, upload queue, processing retry/cancel/restart, result, notifications, and profile logout.
- [ ] Step 2: Implement only missing route wiring and state rendering; reuse existing shared state and theme primitives.
- [ ] Step 3: Ensure every user-visible string uses resources and touch targets meet project accessibility rules.
- [ ] Step 4: Verify no false sensor claim and no fabricated PDF/report UI.
- [ ] Step 5: Run:

```bash
cd mobile
./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest :androidApp:assembleDebug --no-daemon --max-workers=1
```

- [ ] Step 6: Install debug APK on real Android device and manually verify auth -> upload -> processing -> result using safe test account/data. Record screenshot paths and limitations.
- [ ] Step 7: Commit `feat(android): complete pilot athlete flow`.

### Task 10: Web Coach Console Completion

**Deliverable:** web coach can onboard athlete, review analysis, comment, export, and recover from errors.

**Files:** `frontend/src/app/(app)/`, `frontend/src/lib/api/`, `frontend/src/hooks/`, tests, loading/error components.

- [ ] Step 1: Add RED tests for invite, session list, detail, comment, notification, export, stale deep link, unauthorized response, and network retry.
- [ ] Step 2: Connect typed hooks to existing backend contracts; invalidate only affected query keys after mutations.
- [ ] Step 3: Implement loading/empty/error/success states with Russian-first copy and accessible status indicators.
- [ ] Step 4: Run:

```bash
cd frontend
bun test
bun run typecheck
bun run lint
bun run build
```

- [ ] Step 5: Commit `feat(web): complete pilot coach console`.

### Task 11: Production Reliability And Data Safety

**Deliverable:** pilot operations can detect and recover common incidents without data loss.

**Files:** infra compose/deploy config only where needed, backend lifespan/config/health, worker/task manager, monitoring config, new runbooks.

- [ ] Step 1: Add tests for health response, task timeout, orphan cleanup, retry cap, storage failure, database failure, and safe error redaction.
- [ ] Step 2: Add correlation IDs to logs and responses; redact auth headers, signed URLs, and user payloads.
- [ ] Step 3: Verify database migrations with offline SQL:

```bash
cd backend && uv run alembic upgrade head --sql
```

- [ ] Step 4: Document backup frequency, restore command/procedure, queue stuck recovery, storage recovery, and rollback version.
- [ ] Step 5: Add read-only production health smoke; do not expose credentials.
- [ ] Step 6: Commit `chore(ops): harden pilot reliability and recovery`.

### Task 12: Security, Privacy, And Pilot Operations

**Deliverable:** controlled pilot has safe access, support, deletion, and incident procedures.

**Files:** auth/config/CORS/rate-limit code, privacy/support copy, `docs/runbooks/pilot-operations.md`, `docs/runbooks/production-smoke.md`, security tests.

- [ ] Step 1: Add tests for CORS allowlist, rate limits, ownership, IDOR, signed URL expiry, invalid upload MIME/size, and response-body redaction.
- [ ] Step 2: Review refresh token storage/rotation and Android secure storage; no plaintext secrets.
- [ ] Step 3: Write pilot checklist: user enrollment, support contact, deletion request, incident severity, rollback, and data export.
- [ ] Step 4: Run backend security-focused tests and frontend/mobile checks.
- [ ] Step 5: Commit `docs(pilot): define security and operations runbook`.

### Task 13: End-To-End Synthetic And Production Smoke

**Deliverable:** evidence proves the real pilot journey, not merely compilation.

**Files:** `backend/tests/test_e2e_process.py`, new `backend/tests/test_e2e_pilot_contract.py`, `mobile/...` test fixtures, `docs/verification/2026-08-30-pilot-e2e.md`.

- [ ] Step 1: Create deterministic fixture data: one video-only Axel, one synthetic two-sensor stream, one corrupt stream. Mark every fixture.
- [ ] Step 2: Run no-Valkey synthetic contract E2E: upload metadata -> session -> queue -> task events -> result -> notification -> PDF.
- [ ] Step 3: Run safe production smoke with a controlled pilot account and disposable test data; never print tokens or signed URLs.
- [ ] Step 4: Verify restart recovery by killing/reopening client while task is processing; verify no second queue call.
- [ ] Step 5: Record exact timestamps, task/session IDs only if non-sensitive, commands, outputs, and failures.
- [ ] Step 6: Commit `test(pilot): record end to end launch evidence`.

### Task 14: Release Candidate, Device QA, And Pilot Go/No-Go

**Deliverable:** signed release candidate and explicit launch decision.

**Files:** `.github/workflows/android-release.yml`, release docs, `docs/verification/2026-08-30-pilot-readiness.md`, reference screenshots and QA notes.

- [ ] Step 1: Configure GitHub `android-release` environment secrets externally; never add values to repository.
- [ ] Step 2: Run signed APK/AAB workflow, verify signature and SHA-256, upload artifacts.
- [ ] Step 3: Install release APK on real device after removing incompatible prior signature only with explicit operator approval; verify update path using same signing key.
- [ ] Step 4: Perform screenshot/state QA for auth, session list, camera permission, upload, processing, result, notifications, and profile. Compare app content only; exclude device chrome.
- [ ] Step 5: Run final checks:

```bash
# Backend
uv run pytest backend/tests -q --import-mode=importlib --no-cov
uv run ruff check backend/app
uv run basedpyright --level error backend/app

# Frontend
cd frontend && bun test && bun run typecheck && bun run lint && bun run build

# Mobile
cd ../mobile && ./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest :androidApp:assembleDebug --no-daemon --max-workers=1
```

- [ ] Step 6: Classify remaining full-suite failures into product regressions versus infrastructure-only errors; no P0/P1 product failure may be waived.
- [ ] Step 7: Write go/no-go table: happy path, recovery, ownership, privacy, release, support, and known deferred hardware claims.
- [ ] Step 8: Commit `release(pilot): approve SkateLab pilot candidate`.

## Acceptance Gates

### Gate A — Core contract

- [ ] Auth recovery sends `password`.
- [ ] Session and task ownership checks pass.
- [ ] Process queue without click uses auto-detection and does not return 422.
- [ ] Upload and process are idempotent across retry/restart.

### Gate B — Human workflow

- [ ] Coach invites athlete.
- [ ] Athlete accepts and uploads video.
- [ ] Processing completes or fails with actionable recovery.
- [ ] Coach opens result and comments.
- [ ] Athlete receives notification and deep link.
- [ ] Coach exports valid PDF.

### Gate C — Trust and safety

- [ ] No IDOR in pilot routes.
- [ ] No secret/raw-data leakage in logs/errors.
- [ ] Missing sensor data is explicit.
- [ ] Synthetic/unvalidated provenance is visible.
- [ ] Backup/restore and rollback procedures are written and tested.

### Gate D — Release

- [ ] Backend, frontend, shared, Android tests pass or documented infrastructure-only blockers have explicit owner.
- [ ] Debug and signed release artifacts build.
- [ ] Real-device smoke passes.
- [ ] Production health and authenticated pilot smoke pass.
- [ ] Pilot roster and support contact are ready.

## Deferred After Pilot

- Real WT901/EdgeSense hardware acceptance and calibration.
- Accuracy claims and coach-validity study.
- Billing/subscriptions.
- iOS app.
- Broad federation/school administration.
- New ML models and expanded element coverage.
- Fully automated onboarding/support.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-08-30-skatelab-pilot-launch-plan.md`. Execute via `/goal-prep` (recommended, builds a GoalBuddy board) or inline `executing-plans` — choose one before implementation starts.
