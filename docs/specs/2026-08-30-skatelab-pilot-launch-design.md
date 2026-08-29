# SkateLab Pilot Launch Design

**Status:** approved design
**Audience:** first figure-skating coaches and their athletes
**Launch shape:** Android athlete app + web coach console
**Pilot size:** 5-20 users
**Product mode:** video-first; sensors optional and explicitly unvalidated

## Intent

**Why:** Coaches need objective, fast video feedback without spending 10-20 minutes manually reviewing every attempt.

**Human outcome:** Coach uploads or receives an athlete attempt, gets trustworthy actionable feedback in minutes, and can send one clear correction back to the athlete.

**Experience invariants:**
- First useful result is reachable in one short flow.
- Every result distinguishes measured video data from unavailable or unvalidated sensor data.
- Coach always knows processing state, failure reason, and recovery action.
- Athlete sees one prioritized recommendation, not an unexplained metric dump.
- Russian is primary; English remains supported where already implemented.

**Betrayal condition:** Technically complete screens that show invented confidence, silently lose uploads, duplicate processing, or leave coach and athlete without a shared feedback loop are not launch-ready.

## Goals

- Android athlete flow: register/login, invite acceptance, record/select video, upload, durable processing, result, retry, and recovery after restart.
- Web coach flow: invite athlete, list sessions, inspect result, see provenance and recommendation, add coach comment, and export a real report.
- Backend contracts are consistent across auth, sessions, uploads, process/SSE, results, programs, notifications, connections, training plans, reports, and users.
- Production has backups, monitoring, error tracking, rate limits, privacy controls, rollback notes, and a human support runbook.
- Pilot can run without WT901 hardware or payment automation.

## Non-goals

- No public skating-accuracy claim.
- No sensor validation claim before labelled WT901 sessions.
- No iOS client requirement for pilot.
- No new ML model or broad element catalog expansion.
- No automated billing or marketplace.
- No school-wide multi-tenant administration beyond existing workspace primitives.
- No speculative offline-first database redesign.

## Product flows

### Coach onboarding

1. Coach receives access through controlled pilot onboarding.
2. Coach creates or uses account.
3. Coach invites athlete by email or connection flow.
4. Coach sees pending invitation and relationship status.
5. Coach opens athlete sessions and result reports.
6. Coach writes a short comment/recommendation.

### Athlete analysis

1. Athlete registers or logs in.
2. Athlete accepts coach invitation.
3. Athlete chooses element, records video or selects gallery video.
4. App requests camera/storage permissions only when needed.
5. Upload enters durable Room/WorkManager queue.
6. Video upload creates one session.
7. Process queue creates one task with stable ownership; no duplicate queue on restart.
8. SSE observes progress; reconnects only for transient stream interruption.
9. Completed result shows video-derived metrics, phases, recommendation, and provenance.
10. Failed upload/process shows retry/cancel/help and preserves source data until safe cleanup.

### Coach review

1. Coach opens session list with supported server filters and local presentation filters.
2. Coach opens completed result.
3. Result displays overall state, element, take-off/landing evidence, metric definitions, and recommendation context.
4. Sensor section says `video-only`, `unavailable`, or `synthetic/unvalidated`; never implies validated sensor quality.
5. Coach adds comment.
6. Athlete receives typed notification with deep link.
7. Coach exports PDF; response is real `application/pdf`.

## Architecture

```text
Android/KMP athlete client ─┐
                            ├─ Litestar /v1 ─ PostgreSQL
Web coach console ──────────┘                ├─ S3/RustFS
                                             ├─ Valkey/arq
                                             └─ Vast.ai GPU worker
```

### Boundaries

- `mobile/shared/commonMain`: Ktor APIs, serializable wire models, repositories/state machines, typed errors, workflow coordination. No Android/iOS APIs.
- Android: CameraX, BLE, file access, Room, WorkManager, multipart/presigned upload adapters, Compose.
- Backend routes: auth, ownership, validation, response schemas. Routes do not import ML internals.
- Worker: queue ownership, task lifecycle, notification producers, stable ML bridge only.
- ML: inference, decode, fusion, metrics, recommendation inputs. No backend/database/web imports.
- Frontend: coach workflow, query cache, deep links, report presentation, error/empty states.

### Source-of-truth rules

- Backend schemas define HTTP wire shape.
- Shared Kotlin models mirror backend fields with `SerialName` where needed.
- State machines own transitions; screens observe state and do not duplicate business rules.
- One queue owner persists `processTaskId`; all later observers use it.
- Ownership checks happen before expensive work and before report generation.
- Missing, invalid, synthetic, and measured data are distinct states.

## Contract matrix

| Domain | Required pilot contract | Acceptance |
|---|---|---|
| Auth | register/login/refresh/logout/forgot/reset/verify/resend | exact field names, typed errors, token persistence and expiry recovery |
| Connections | invite/pending/accept/end | no IDOR; coach-athlete visibility explicit |
| Sessions | create/list/get/patch/delete/bulk delete | supported query params only; cursor pagination; ownership |
| Uploads | presign/init/complete | resumable-safe state, content type/size checks, no lost local file |
| Process | queue/status/cancel/SSE | optional person click enables auto-detection; stable task ID; terminal SSE |
| Results | session metrics/phases/scores/diagnostics | unavailable states and provenance visible |
| Notifications | list/unread/read/read-all/deep links | producers for analysis, training, comments, export |
| Training | generate/get | idempotent per session and typed state |
| Reports | PDF/SVG/JSON export | valid content type, disposition, ownership |
| Programs | CRUD/choreography/music analysis | pilot-safe, no fake successful upload |
| User/profile | settings/onboarding/avatar/logout | validation, privacy, deletion/support path |

## State and recovery contract

### Upload states

`READY -> UPLOADING -> PROCESSING -> COMPLETED`

Failure branches preserve source files:

`UPLOADING -> NETWORK_ERROR -> READY`

`UPLOADING/PROCESSING -> FAILED -> READY or terminal failure after retry cap`

### Analysis states

`Draft -> Capture -> Uploading -> Queued(taskId absent) -> Queued(taskId present) -> Processing -> Completed`

Terminal states: `Failed`, `Cancelled`.

Rules:

- Queue call occurs once per workflow ID.
- Reopening app with `processTaskId` observes existing task; never queues again.
- SSE auth/server errors propagate; transient stream interruption reconnects within bounded attempts.
- Cancellation is idempotent and never deletes source files before terminal confirmation.
- A completed server result is never downgraded by a late stream event.

## Data honesty

- Video-only result: show `Video-only analysis`.
- Missing one/both sensors: show `Sensor fusion unavailable` and reason.
- Synthetic fixture: show `Synthetic / unvalidated`.
- Corrupt/truncated stream: fail closed; no fused score.
- Confidence describes model/data confidence, not sports validity.
- Recommendation copy names observed evidence and one next action.

## Security and privacy

- Never log access tokens, passwords, signed URLs, raw video, IMU payloads, or private profile data.
- Enforce ownership on every session, task, notification, program, plan, connection, and export.
- Validate upload extension, MIME type, size, and storage key ownership.
- Use short-lived signed URLs.
- Rate-limit auth, process, detect, exports, invitations, and plan generation.
- Provide pilot user deletion/export support procedure.
- Keep production secrets in CI/environment only.
- Review CORS, cookie/token storage, refresh rotation, and error-body leakage before pilot.

## Observability and support

- Track request ID, user-safe operation ID, session ID, task ID, and workflow ID without raw data.
- Metrics: upload success/failure, queue latency, processing latency, SSE disconnects, retry counts, completed/failed sessions, report exports, notification delivery.
- Alerts: API health, queue backlog, GPU failure rate, storage failures, database saturation, certificate expiry.
- Sentry/error tracking strips credentials and payloads.
- Support runbook covers stuck upload, stuck processing, failed export, account recovery, deletion request, and rollback.

## Release gates

### Must pass before pilot

- Backend focused contract suite and migration offline SQL.
- Shared and Android unit tests, lint, type checks, debug build.
- Frontend tests, typecheck, lint, production build.
- One synthetic end-to-end run without Valkey startup on developer machine.
- Production health smoke and authenticated staging/pilot smoke.
- Android install/update smoke on a real device.
- Coach invite -> athlete upload -> completed result -> comment -> notification -> PDF smoke.
- Backup restore drill and rollback note.
- Privacy/support copy and pilot user list prepared.

### Explicitly blocked until later

- WT901 hardware acceptance.
- Claims about biomechanical or sensor accuracy.
- Paid billing.
- iOS release.
- Broad public launch.

## Definition of done

Pilot is launch-ready only when a coach and athlete can complete the full happy path, recover from network/app restart, understand every unavailable state, and reach human support. All changed contracts have tests. Production smoke evidence is recorded in `docs/verification/`. No known P0/P1 defects remain in auth, ownership, upload, process, result, notification, report, or release paths.
