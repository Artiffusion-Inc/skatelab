# Pilot operations runbook

Status: operational checklist for the 5-20 user video-first pilot. This runbook is
not a deployment procedure. Use the existing platform controls for production
changes and record the release commit separately.

Canonical references:

- [Production smoke](production-smoke.md)
- [Backup, restore, and rollback](backup-restore-rollback.md)
- [Secret rotation](secret-rotation.md)
- [Release artifact verification](release-artifact-verification.md)
- [Approved pilot design](../specs/2026-08-30-skatelab-pilot-launch-design.md)

## Safety rules

- Use a dedicated pilot smoke account and disposable test data. Never use an athlete's real video for an operational check.
- Do not paste passwords, access tokens, signed URLs, raw video, IMU payloads, or private profile data into tickets, logs, CI summaries, or release notes.
- Record only UTC time, release commit or image digest, HTTP status, redacted correlation ID, and non-sensitive session/task IDs when necessary.
- Do not delete a source video, database volume, or object-storage prefix while investigating an incident.
- Do not run database downgrades, volume deletion, or production deploy commands from this document without explicit owner approval.

## Incident levels

| Level | Trigger | First action |
| --- | --- | --- |
| P0 | Suspected data exposure, cross-user access, credential exposure, or data loss | Stop pilot writes, preserve evidence, revoke exposed credentials, and page the incident owner. |
| P1 | Core login, upload, processing, result, or ownership path is unavailable for multiple users | Freeze release activity, run the safe production smoke, and page the service owner. |
| P2 | One user or non-critical feature is impaired | Capture a redacted operation ID, provide the documented recovery path, and track a support ticket. |

The pilot owner decides whether to pause new uploads. Do not announce recovery until
both the smoke run and the affected user journey pass.

## Initial triage

1. Note the UTC start time, reporter, affected flow, release commit or image digest, and a redacted operation ID.
2. Run the unauthenticated health check from [Production smoke](production-smoke.md). Do not print the response body.
3. If health is `degraded`, treat Valkey or a dependent service as unavailable; do not repeatedly retry writes.
4. Check platform logs and metrics using their redaction controls. Search by operation ID, session ID, or task ID, never by email, token, URL, or video filename.
5. Check whether the source file and server task/session state still exist before asking the user to retry.

## Stuck upload

- Ask the user to keep the local source file and leave the app open only if it is safe to do so; never ask for a password or a token.
- Confirm whether a session ID, upload state, or process task ID was persisted. Resume the existing workflow when an ID exists; do not create a second session or queue a second task.
- If no task ID exists and the source file is still present, allow one bounded retry. Do not retry after an unknown server response until the existing session is checked.
- If the upload is complete but processing was not queued, record the session ID and use the approved support/admin path to reconcile it. Do not edit storage keys by hand.
- Escalate as P1 when two or more users are affected or when source data cannot be located.

## Stuck processing

- Poll the task status with the authenticated client or the safe support tooling. A terminal `completed`, `failed`, or `cancelled` state must not be changed by a late retry.
- Check queue backlog, worker availability, and storage/database alerts before retrying. Do not start a local Valkey instance as a production workaround.
- If the client was restarted, reopen the workflow and observe its persisted task ID. Never queue again solely because the progress screen was reset.
- Cancel only when the user requested cancellation or the incident owner approved it. Cancellation is idempotent and must not remove the source file before terminal confirmation.
- Use one bounded retry for a transient failure. Preserve the original failure and task IDs in private incident notes.

## Failed result or export

- Keep the session and source data available until the user has received a result or the deletion request is complete.
- A failed analysis is not a valid video result. Do not tell a user that missing or corrupt sensor data was successful, and do not infer skating accuracy from a confidence value.
- Retry export only from a completed, owned session. If it fails again, capture the HTTP status and operation ID and escalate; do not generate a substitute file or mark the export ready manually.
- For a stale notification or deep link, send the user to the notifications/session list and explain that the original target is unavailable. Do not disclose another user's data.

## Account and privacy requests

- Account recovery uses the product's password-reset flow. Support staff never request, receive, or store a user's password or reset token.
- For deletion or export, verify the requester's account through the approved support process before acting. Record request and completion timestamps, not the exported content.
- Deletion must cover the account-owned database records and object-storage objects, with backup retention handled by the [backup runbook](backup-restore-rollback.md). Do not remove shared volumes or unrelated prefixes.
- If a request may involve a minor's data, suspected unauthorized access, or a legal hold, pause the request and escalate to the privacy owner.

## Rollback and recovery

Use [Backup, restore, and rollback](backup-restore-rollback.md). In short:

1. Freeze further release activity and capture a pre-recovery backup.
2. Prefer an application-image rollback to the last verified immutable release when the database schema is compatible.
3. Never run `alembic downgrade` or restore over the live database as a first response.
4. Run [Production smoke](production-smoke.md), then verify the affected pilot journey with disposable data.
5. If data recovery is required, restore to an isolated target first and obtain owner approval before any controlled cutover.

## Closeout

- Confirm the service smoke, affected user journey, and queue/storage state are healthy.
- Record impact window, release identity, root cause, recovery action, and follow-up owner without private data.
- Revoke temporary credentials and remove temporary local files using the approved secure deletion process.
- For P0/P1 incidents, obtain incident-owner sign-off before resuming pilot writes or declaring the incident closed.
