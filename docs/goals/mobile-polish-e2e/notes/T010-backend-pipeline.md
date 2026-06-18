# T010 Scout: Backend Processing Pipeline Health

## Findings

### Backend Health
- `/v1/health` → `{"status":"ok","valkey":true}` — backend alive, Valkey connected
- `/v1/process/queue` → 401 (JWT required) — endpoint works
- `/v1/sessions` → 200 (empty list for test user)

### Processing Pipeline Architecture
1. Mobile app uploads video via ChunkedUploader → S3/RustFS
2. UploadWorker creates session via `POST /sessions` → gets `session.id`
3. UploadWorker enqueues processing via `POST /process/queue` → gets `task_id`
4. arq worker picks up task → dispatches to Vast.ai Serverless GPU
5. Vast.ai processes video → returns poses + metrics
6. Worker saves results to DB → publishes events via Valkey pub/sub
7. Mobile app streams progress via `GET /process/{task_id}/stream` (SSE)

### Critical Bugs Found
1. **videoKey (r2Key) not saved to Room** — UploadWorker gets videoKey from ChunkedUploader but never writes it to PendingUploadEntity. ProcessingScreen reads `entity.r2Key ?: ""` — always empty.
2. **sessionId not set at PROCESSING status** — `updateStatus(entity.id, "PROCESSING")` called without sessionId. But `observeUpload()` checks `entity.sessionId` to transition to ReadyForProcessing.
3. **No progress bar during upload** — UploadStatusContent shows only spinner.

### Worker Status
- Cannot verify arq worker is running remotely (no SSH access)
- Worker requires VASTAI_API_KEY — raises RuntimeError if missing
- Worker startup retries Valkey connection 5 times with backoff

### SSE Stream
- Implemented with Valkey pub/sub
- 60-second timeout (`SSE_STREAM_TIMEOUT`)
- Reconnect logic in mobile ProcessApi (3 retries with exponential backoff)
- Ownership check: rejects if task belongs to another user

### Recommendation
- Fix bugs T011 first (videoKey, sessionId, r2Key rename)
- Then test upload→processing flow on real device against api.skatelab.ru
- If processing doesn't trigger, check arq worker logs on production