# SkateLab Android MVP Implementation Plan

> **For agentic workers:** After this plan is written, present the execution gate to the user (`/goal-prep` board vs inline executing-plans). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SkateLab Android software-complete for a synthetic-data pilot while hardware validation is unavailable, without claiming sensor accuracy.

**Architecture:** Keep Android as the capture client and keep KMP networking/state platform-neutral. Use deterministic recorded fixtures and mocked BLE for development; production still accepts real LEFT/RIGHT WT901 streams through the same `.binpb` and manifest contracts. Ship one end-to-end Axel slice: capture/replay -> S3 -> backend session -> GPU decode/fusion -> SSE result -> coach report.

**Tech Stack:** Kotlin Multiplatform, Android Compose, CameraX, Hilt, Room, WorkManager, Ktor, WT901 BLE abstraction, Python 3.11, Litestar, arq, S3/RustFS, CUDA GPU worker, pytest, Ruff, basedpyright, Gradle/Ktlint.

## Global Constraints

- Work directly on `master`; do not create branches or worktrees.
- Preserve unrelated dirty changes; never reset, checkout, clean, stash, or rewrite user work.
- Commit validated deliverables automatically and push to `origin/master`.
- Do not claim hardware validation, skating accuracy, or coach validity until real WT901 sessions are collected and labelled.
- Keep exactly one public product slice: one Axel flow and one take-off/landing edge metric.
- Require both sensor streams for multimodal mode; never silently downgrade a failed sensor to valid data.
- Keep `commonMain` free of Android/iOS APIs.
- Do not add new dependencies unless an existing project dependency cannot solve the requirement.
- Do not run Valkey locally; use mocked/unit paths or already available production smoke endpoints.
- Use `./gradlew --no-daemon --max-workers=1`; preserve existing Java/SDK environment requirements.
- Synthetic fixtures must be explicitly marked `synthetic` or `unvalidated` in reports and test data.
- Never print or commit credentials, tokens, passwords, raw user data, or production `.env` values.

## Current State

Already present on `master`:

- Android camera + BLE capture flow with LEFT/RIGHT `.binpb` writers.
- Manifest creation and upload of video, both IMU streams, and manifest.
- Backend session fields for `imu_left_key`, `imu_right_key`, and `manifest_key`.
- Worker/GPU key propagation and GPU-side IMU decoder.
- Deterministic sensor-fusion diagnostics and metrics.
- Room persistence of `processTaskId` and existing-task SSE recovery.
- Production API at `https://api.skatelab.ru/v1/`.
- Debug APK build and mobile unit/shared tests.

Known limits:

- No real hardware for approximately one month.
- Sensor-fusion thresholds and metrics are unvalidated heuristics.
- Full backend local suite still has Valkey-dependent setup paths.
- Android release signing and full device smoke remain open.
- iOS is not a runnable client and stays out of this plan.

## File Map

### Synthetic capture and contract fixtures

- Create `ml/tests/sensor_fusion/fixtures/` — small deterministic valid, gap, drift, and corrupt `.binpb`/manifest fixtures.
- Create `backend/tests/fixtures/` only if backend contract tests need a separate payload fixture; do not duplicate binary fixtures without reason.
- Modify `ml/tests/sensor_fusion/test_binpb_fixture.py` — lock Android length-delimited wire contract and corruption behavior.
- Modify `ml/tests/sensor_fusion/test_features.py` — lock deterministic fusion feature behavior and explicit unvalidated semantics.

### Android mocked capture and recovery

- Modify `mobile/androidApp/src/test/java/ru/skatelab/capture/data/recording/ImuCollectorTest.kt` — cover two-sensor replay and writer lifecycle.
- Modify `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/camera/CameraViewModelTest.kt` — cover start failure cleanup, stop manifest creation, and pending upload creation.
- Modify `mobile/androidApp/src/test/java/ru/skatelab/capture/upload/UploadWorkerTest.kt` — cover upload/process task persistence and retry state.
- Modify `mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/FakePendingUploadDao.kt` — maintain fake behavior for task IDs and recovery.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt` — only where tests expose lifecycle or manifest defects.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt` — only where tests expose retry/idempotency defects.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModel.kt` — only where restart/recovery tests expose state defects.

### Backend/GPU E2E contract

- Modify `backend/app/schemas.py` — keep process/task response fields explicit and nullable where sensor data is unavailable.
- Modify `backend/app/worker.py` — preserve sensor diagnostics in task result and distinguish absent from invalid streams.
- Modify `backend/app/vastai/client.py` — preserve all multimodal request fields.
- Modify `ml/gpu_server/server.py` — keep download/decode/fusion pipeline deterministic and fail closed on corrupt input.
- Modify `ml/src/sensor_fusion/imu_decoder.py` — only for fixture-discovered wire/validation defects.
- Modify `ml/src/sensor_fusion/features.py` — only for deterministic feature defects, not threshold tuning without labelled data.
- Create `backend/tests/test_sensor_fusion_e2e_contract.py` — worker request/result contract without requiring Valkey.
- Create `ml/tests/sensor_fusion/test_gpu_process_contract.py` — GPU request fixture and result payload smoke coverage.

### Report and release readiness

- Modify `frontend/src/app/(app)/sessions/[id]/page.tsx` — show sensor provenance and `unvalidated` state; no new dashboard surface.
- Modify `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt` — show diagnostics and provenance without presenting heuristics as scores.
- Create `docs/verification/2026-08-29-android-mvp-synthetic-validation.md` — measured commands, fixture results, and known limits.
- Create `docs/runbooks/android-release-smoke.md` — release build, install, production API, mocked BLE, and later hardware handoff.

## Implementation Tasks

### Task 1: Lock Synthetic Multimodal Capture Contract

**Deliverable:** deterministic fixtures prove that Android-format streams, manifest timing, gaps, drift, truncation, and both-sensor requirements are handled consistently.

**Files:** `ml/src/sensor_fusion/imu_decoder.py`, `ml/src/sensor_fusion/features.py`, `ml/tests/sensor_fusion/test_binpb_fixture.py`, `ml/tests/sensor_fusion/test_features.py`, `ml/tests/sensor_fusion/fixtures/`.

- [ ] **Step 1: Write failing tests** for valid delimited records, gap records, non-monotonic timestamps, truncated records, missing manifest anchor, and asymmetric left/right streams.
- [ ] **Step 2: Run focused RED checks:**

```bash
uv run pytest ml/tests/sensor_fusion -q --import-mode=importlib --no-cov
```

Expected: new tests fail only where contract is not implemented.

- [ ] **Step 3: Add the smallest fixture and decoder changes.** Preserve dependency-free protobuf parsing. Reject truncation and non-monotonic timestamps. Keep `0 ms` and `0 Hz` values distinct from missing values.
- [ ] **Step 4: Run GREEN checks:**

```bash
uv run pytest ml/tests/sensor_fusion -q --import-mode=importlib --no-cov
uv run ruff check ml/src/sensor_fusion ml/tests/sensor_fusion
uv run basedpyright --level error ml/src/sensor_fusion
```

Expected: all sensor-fusion tests pass; no type errors in sensor-fusion package.

- [ ] **Step 5: Commit:**

```bash
git add ml/src/sensor_fusion ml/tests/sensor_fusion
git commit -m "test(ml): lock synthetic multimodal capture contract"
git push origin master
```

### Task 2: Make Android Capture Replayable Without Hardware

**Deliverable:** mocked BLE and deterministic fixture replay exercise camera start/stop, both writers, manifest creation, upload enqueue, and process-task recovery.

**Interfaces:** `ImuCollector` receives both `SensorId.LEFT` and `SensorId.RIGHT` output files. `PendingUploadEntity` carries `manifestPath`, both IMU paths, and optional `processTaskId`. `UploadWorker` persists `PROCESSING` plus task ID after one queue call.

**Files:** `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt`, `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt`, `mobile/androidApp/src/test/java/ru/skatelab/capture/data/recording/ImuCollectorTest.kt`, `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/camera/CameraViewModelTest.kt`, `mobile/androidApp/src/test/java/ru/skatelab/capture/upload/UploadWorkerTest.kt`, `mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/FakePendingUploadDao.kt`.

- [ ] **Step 1: Add failing tests** for both writers starting before stream collection, stop closing both writers, manifest being valid JSON before WorkManager enqueue, and a failed recording start stopping/clearing the collector.
- [ ] **Step 2: Run RED checks:**

```bash
cd mobile
./gradlew :androidApp:testDebugUnitTest --no-daemon --max-workers=1
```

Expected: tests fail only for missing lifecycle/replay behavior.

- [ ] **Step 3: Implement minimal lifecycle fixes.** Do not add a second capture abstraction. Use existing injected `ImuCollector`, existing `StartRecordingUseCase`, existing Room DAO, and existing `UploadScheduler`.
- [ ] **Step 4: Add recovery test** proving an entity with `processTaskId` calls `observeTask(taskId)` and never `process.queue()` again.
- [ ] **Step 5: Run GREEN checks:**

```bash
cd mobile
./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest :androidApp:assembleDebug --no-daemon --max-workers=1
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 6: Commit:**

```bash
git add mobile/androidApp mobile/shared
 git commit -m "test(android): make multimodal capture replayable"
git push origin master
```

### Task 3: Verify Backend/GPU Synthetic E2E

**Deliverable:** one no-Valkey test path proves all three uploaded artifact keys reach GPU, decode successfully, and return diagnostics with provenance.

**Interfaces:** backend process request carries `imu_left_key`, `imu_right_key`, and `manifest_key`; GPU process response carries sensor diagnostics under an explicit `sensor_fusion` result object; absent data is `null`/unavailable, corrupt data is an error.

**Files:** `backend/app/schemas.py`, `backend/app/worker.py`, `backend/app/vastai/client.py`, `ml/gpu_server/server.py`, `backend/tests/test_sensor_fusion_e2e_contract.py`, `ml/tests/sensor_fusion/test_gpu_process_contract.py`.

- [ ] **Step 1: Write failing contract tests** asserting request propagation, response preservation, and rejection of corrupt streams.
- [ ] **Step 2: Run RED checks without Valkey:**

```bash
uv run pytest backend/tests/test_sensor_fusion_e2e_contract.py ml/tests/sensor_fusion/test_gpu_process_contract.py -q --import-mode=importlib --no-cov
```

Expected: failures identify missing propagation or result fields, not service startup errors.

- [ ] **Step 3: Implement the smallest propagation/result changes.** Do not start Valkey and do not bypass typed schemas with broad dictionaries unless the surrounding API already uses them.
- [ ] **Step 4: Run GREEN checks:**

```bash
uv run pytest backend/tests/test_sensor_fusion_e2e_contract.py ml/tests/sensor_fusion -q --import-mode=importlib --no-cov
uv run ruff check backend/app ml/src
uv run basedpyright --level error backend/app ml/src
```

Expected: focused tests pass; basedpyright reports zero errors.

- [ ] **Step 5: Run production read-only smoke:**

```bash
curl --fail --silent --show-error https://api.skatelab.ru/v1/health
```

Expected: JSON health response, not HTML.

- [ ] **Step 6: Commit:**

```bash
git add backend ml
git commit -m "test(api): verify synthetic sensor fusion e2e contract"
git push origin master
```

### Task 4: Make Report and Release Pilot-Ready

**Deliverable:** Android/frontend reports clearly show sensor provenance, synthetic/unvalidated status, diagnostics, and one Axel recommendation; debug and release artifacts have reproducible checks.

**Files:** `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/session/SessionDetailScreen.kt`, `frontend/src/app/(app)/sessions/[id]/page.tsx`, `docs/verification/2026-08-29-android-mvp-synthetic-validation.md`, `docs/runbooks/android-release-smoke.md`.

- [ ] **Step 1: Write failing UI/contract tests** for absent IMU, synthetic fixture, valid multimodal result, and corrupt-stream error display. Use visible text selectors for Compose/automation.
- [ ] **Step 2: Run RED checks** using existing mobile/frontend test commands; do not weaken selectors or assertions to force a pass.
- [ ] **Step 3: Implement minimal honest presentation:** show `Sensor fusion: unavailable`, `synthetic/unvalidated`, or measured diagnostics. Never render confidence as skating quality.
- [ ] **Step 4: Run GREEN checks:**

```bash
cd mobile
./gradlew ktlintCheck :shared:allTests :androidApp:testDebugUnitTest :androidApp:assembleDebug --no-daemon --max-workers=1
cd ../frontend
bun run test
bun run typecheck
bun run lint
```

Expected: all changed-scope checks pass and APK is produced.

- [ ] **Step 5: Write measured verification** with fixture IDs, commands, output, limitations, and explicit `hardware validation pending` status.
- [ ] **Step 6: Commit:**

```bash
git add mobile frontend docs/verification docs/runbooks
git commit -m "docs(mobile): define synthetic pilot readiness"
git push origin master
```

## Acceptance Criteria

### Software acceptance before hardware

- [ ] Valid synthetic LEFT + RIGHT streams pass decode and fusion.
- [ ] Missing one sensor blocks multimodal completion or reports unavailable; no silent success.
- [ ] Corrupt/truncated stream fails visibly and does not produce a valid fused result.
- [ ] Manifest anchor and per-sensor timestamps reach GPU.
- [ ] Backend task result preserves sensor diagnostics and provenance.
- [ ] Android upload calls process queue exactly once.
- [ ] App restart observes persisted task ID instead of re-queueing.
- [ ] Retry and cancel preserve correct task/session state.
- [ ] Production health endpoint returns SkateLab JSON.
- [ ] Debug APK builds; release signing status is documented honestly.
- [ ] Report labels synthetic data as unvalidated.

### Hardware acceptance after sensors arrive

- [ ] 10-20 real Axel attempts from 3-5 skaters.
- [ ] Both streams contain samples and monotonic timestamps.
- [ ] `imu_offset_error <= 40 ms` in at least 90% of attempts.
- [ ] `imu_rate_error <= 5 Hz` in at least 90% of attempts.
- [ ] `sensor_confidence >= 0.6` in at least 90% of attempts.
- [ ] Coach labels take-off/landing and compares one metric.
- [ ] Only after this gate: decide whether to tune features, change workflow, or expand elements.

## Deferred

- Real WT901 validation and calibration.
- New elements beyond Axel.
- New ML models.
- Public accuracy claims.
- Full iOS client.
- Hardware replacement.
- Complex calibration metadata model.
- Pricing and paid pilot claims based on sensor metrics.

## Execution Handoff

This document is a plan, not permission to execute automatically. Recommended next action: run Task 1 first, then Task 2, then Task 3, then Task 4. Each task ends with its own tests, commit, and push. Hardware acceptance resumes when WT901 access returns.
