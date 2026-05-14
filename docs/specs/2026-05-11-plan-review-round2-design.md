# Mobile Parallelism Plan Review — Round 2 Agent Findings

**Date:** 2026-05-11
**Status:** Final
**Reviewed plan:** `docs/plans/2026-05-11-mobile-parallelism-async.md` (updated with Round 1 findings I1-I13)
**Previous review:** `docs/specs/2026-05-11-plan-review-design.md`

> 4 specialized agents reviewed the updated plan: BLE Pipeline, IMU/Recording, I/O Threading, Parallelization Strategist. All completed successfully.

---

## Summary of All Findings (Deduplicated)

### Critical (2)

| # | Agent | Finding | Fix |
|---|-------|---------|-----|
| R2-1 | Parallelization | **T14 must precede T11** — ImuCollector rewrite calls `writer.flush()` but `flush()` method doesn't exist until T14 adds it. Compilation error. | Move T14 to Phase 1 (ImuStreamWriter.kt not touched by any Phase 1 task) |
| R2-2 | BLE | **writeQueue/writeInProgress not cleaned on disconnect** — stale entries processed against new GATT after reconnect, causing duplicate commands | Clear `writeQueue[address]` + `writeInProgress[address] = false` in `disconnect()` and `onConnectionStateChange(STATE_DISCONNECTED)` |

### High (7)

| # | Agent | Finding | Fix |
|---|-------|---------|-----|
| R2-3 | IMU | **counts[id] = counts.getOrDefault(id, 0) + 1 is non-atomic** on ConcurrentHashMap — read-modify-write race | Use `AtomicInteger` per sensor: `counts[id]!!.incrementAndGet()` |
| R2-4 | IMU | **ImuCollectorTest flaky after P6** — `Dispatchers.IO` not controlled by TestScope, `advanceUntilIdle()` won't advance real IO threads | Inject `ioDispatcher: CoroutineDispatcher = Dispatchers.IO` into ImuCollector for testability |
| R2-5 | IMU | **imuCollector.stop() exception kills stopRecording** — if ImuStreamWriter.close() throws, entire coroutine cancels, UI stuck in "recording" | Wrap in try/catch: `val imuCounts = try { withContext(IO) { imuCollector.stop() } } catch ...` |
| R2-6 | BLE | **recordingSensors (mutableSetOf) not thread-safe** — accessed from Binder thread (isRecording in onConnectionStateChange) + Main (markRecording/markStopped) | Replace with `ConcurrentHashMap.newKeySet<SensorId>()` |
| R2-7 | I/O | **ExportViewModel _isExporting stuck on cancellation** — `_isExporting.value = false` after `withContext(IO)` block; CancellationException skips it | Wrap in `try/finally { _isExporting.value = false }` |
| R2-8 | I/O | **FrameTimestampTracker scope injection chain incomplete** — plan requires CoroutineScope but never specifies how Camera2Recorder/CameraRepositoryImpl obtain it; no scope cancellation; no test for new constructor | Use simpler `LinkedBlockingQueue` bounded approach instead of full coroutine rewrite; avoids DI chain change |
| R2-9 | I/O | **Camera2Recorder no guard against double startRecording()** — calling twice leaks old capture session + FrameTimestampTracker | Add guard: `if (captureSession != null) throw IllegalStateException("Already recording")` |

### Medium (8)

| # | Agent | Finding | Fix |
|---|-------|---------|-----|
| R2-10 | IMU | **start() only cancels flushJob, not collectJobs/reconnectJob/streamingJob** from previous session — double-start creates duplicate writers | Cancel all previous jobs at start of `start()`: add `collectJobs.values.forEach { it.cancel() }; collectJobs.clear()` etc. |
| R2-11 | IMU | **stop() doesn't clear lastSampleNs** — stale values on re-start cause wrong gap computation | Add `lastSampleNs.clear()` to `stop()` |
| R2-12 | IMU+I/O | **collectJobs uses mutableMapOf** — `stop()` from `runBlocking(IO)` in onCleared races with `start()` on Main | Use `ConcurrentHashMap<SensorId, Job>()` |
| R2-13 | BLE | **activeScanCallback not cleaned if startScan() throws** (SecurityException on Android 12+) | Wrap `scanner.startScan()` in try-catch; null out callback on exception |
| R2-14 | BLE | **activeScanCallback not @Volatile** — TOCTOU race if stopScan called off-Main | Add `@Volatile` annotation |
| R2-15 | I/O | **LaunchedEffect(outputDir) restarts on every recomposition** — `System.currentTimeMillis()` creates new File instance each time | Use `remember { File(...) }` + `LaunchedEffect(Unit) { outputDir.mkdirs() }` |
| R2-16 | I/O | **runCatching swallows CancellationException in deleteSession** — prevents proper coroutine cancellation | Re-throw CancellationException: `catch (e: CancellationException) { throw e } catch (e: Exception) { Result.failure(e) }` |
| R2-17 | Parallelization | **Critical path in plan header is wrong** — says "T3→T4→T6→T8→T11→T15" but correct is "T2→T8→T9→T11→T14→T15" | Fix header text |

### Low (4)

| # | Agent | Finding | Fix |
|---|-------|---------|-----|
| R2-18 | BLE | **updateConnectionState not atomic across sensors** — two GATT callbacks from different sensors can lose one update | Use `_connectionState.update { current -> current + (sensorId to state) }` |
| R2-19 | IMU | **runBlocking(IO) in onCleared safe** — stop() is synchronous, no Main dispatcher needed | Add comment documenting assumption |
| R2-20 | I/O | **ExportViewModelTest constructor mismatch** — test passes 3 args, actual constructor takes 2 | Fix test to match actual constructor signature |
| R2-21 | I/O | **StateFlow values set from IO thread** — cosmetic one-frame delay in Compose | Document as intentional; no fix needed |

---

## Parallelization Optimizations

| # | Recommendation | Impact |
|---|----------------|--------|
| O1 | **Move T14 (ImuStreamWriter.flush) to Phase 1** — fixes compilation error AND optimizes schedule (no Phase 1 conflict) | Critical fix + schedule compression |
| O2 | **Move T12 (P8, Camera2Recorder) to Phase 1** — Camera2Recorder.kt not touched by any Phase 1 task | Reduces Phase 3 to just T11 |
| O3 | **Move T10 (P15, FrameTimestampTracker) to Phase 1** — independent file (if using simpler LinkedBlockingQueue approach per R2-8) | Reduces Phase 2 to T7+T8+T9 |
| O4 | **T17 and T18 must be sequential in Phase 5** — both touch AppNavigation.kt | Prevents merge conflict |
| O5 | **Phase 1 git merge: sequential commits** — subagents should not commit simultaneously | Prevents git race |

### Revised Optimal Phase Layout

```
Phase 1 (9 parallel tasks, no file conflicts):
  T1(P2), T2(P4), T3(P7), T4(P12), T5(P13), T6(P17),
  T10(P15)*, T12(P8), T14(P11 - ImuStreamWriter.flush only)

Phase 2 (sequential within file groups):
  T7(P3) — after T1 (same file: RecordingVM)
  T8(P5) — after T2 (same file: BleManager)
  T9(P10) — after T8 (same file: BleManager)

Phase 3 (1 task):
  T11(P6) — after T9 + T14 (flush() exists, buffer increased)

Phase 4 (2 parallel tasks):
  T13(P9) — after T12 (same file: Camera2Recorder)
  T15(P16) — after T14 (same file: ImuStreamWriter)

Phase 5 (sequential):
  T16(P14) — after T9 (same file: BleManager)
  T17(P18) — independent
  T18(P19) — after T17 (same file: AppNavigation.kt)
```

*T10 uses simpler LinkedBlockingQueue approach per R2-8, removing CoroutineScope injection requirement.*

**Critical path:** T2→T8→T9→T11 (4 sequential hops, down from 6)

**Time savings:** Phase 1 absorbs 3 additional tasks. Phase 3 reduced to 1 task. Overall wall-clock reduction ~30% vs current 5-phase plan.

---

## Plan Changes Required

### Tasks to Modify

| Task | Change | Reason |
|------|--------|--------|
| T1 (P2) | Wrap `imuCollector.stop()` in try/catch | R2-5: exception kills stopRecording |
| T2 (P4) | Add try-catch around `scanner.startScan()`, add `@Volatile` to `activeScanCallback` | R2-13, R2-14 |
| T3 (P7) | Add `try/finally { _isExporting.value = false }` to ExportViewModel; fix `runCatching` in `deleteSession` to re-throw CancellationException | R2-7, R2-16 |
| T8 (P5) | Also add try-catch around `device.connectGatt()` | R2-13 pattern (defensive) |
| T10 (P15) | Use `LinkedBlockingQueue(1000)` instead of coroutine Channel + CoroutineScope; no DI chain change needed | R2-8: scope injection incomplete |
| T11 (P6) | Use `AtomicInteger` for counts; inject `ioDispatcher` for testability; cancel all previous jobs at start of `start()`; add `lastSampleNs.clear()` to stop(); use `ConcurrentHashMap` for `collectJobs` | R2-3, R2-4, R2-10, R2-11, R2-12 |
| T12 (P8) | Add guard `if (captureSession != null) throw IllegalStateException` | R2-9 |
| T14 (P11) | Move to Phase 1 | R2-1: compilation dependency |

### Tasks to Add

| Task | Description | Reason |
|------|-------------|--------|
| T19 | Add `ConcurrentHashMap.newKeySet()` for `recordingSensors` in BleManager.kt | R2-6: thread-safety |
| T20 | Add `_connectionState.update {}` in `updateConnectionState()` | R2-18: atomic state update |
| T21 | Clean `writeQueue`/`writeInProgress` on disconnect and STATE_DISCONNECTED | R2-2: stale queue entries |

### Structural Changes

| Change | Reason |
|--------|--------|
| Fix critical path in header | R2-17: wrong path listed |
| Move T14 to Phase 1 | R2-1: compilation dependency |
| Move T12 to Phase 1 | O2: optimization |
| Move T10 to Phase 1 (with LinkedBlockingQueue approach) | O3: optimization |
| Mark T18 as dependent on T17 | O4: same file conflict |
