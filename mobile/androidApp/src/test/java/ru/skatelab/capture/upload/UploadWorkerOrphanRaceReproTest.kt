package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.WorkerParameters
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.shared.api.SkateLabClient

/**
 * Repro for issue #330 — upload-init hangs forever on "Preparing upload…" (orphaned PendingUpload).
 *
 * Root cause (RC-углубление): `UploadWorker.doWork()` returns `Result.success()` when
 * `pendingUploadDao.tryLockForUpload(uploadId) == 0` (UploadWorker.kt:54). `tryLockForUpload` is
 * `UPDATE pending_uploads SET status='UPLOADING' WHERE id=:id AND status='READY'` (returns rows
 * affected). When the UPDATE matches 0 rows — which happens on the insert→enqueue RACE
 * (CameraViewModel.kt:273-275 / :206-210: `pendingUploadDao.insert(...)` then
 * `UploadScheduler.enqueue(...)` in the same coroutine, but the WorkManager worker starts BEFORE
 * the Room insert commits → the row is absent or not-yet-READY at worker-run) — the worker exits
 * `Result.success()` WITHOUT doing any work. WorkManager marks the job SUCCEEDED (run_attempt_count=0),
 * so it NEVER retries. The PendingUpload row stays `status=READY` forever → UI shows
 * "Preparing upload…" indefinitely (no "No connection"/"Retry", no timeout, no recovery).
 *
 * DB evidence (emulator skatelab-emulator-2, U2 repro):
 *  - PendingUpload Room: `status=READY, retryCount=0, videoKey=(empty)` (worker never updated status)
 *  - WorkManager workspec: `state=3 (SUCCEEDED), run_attempt_count=0` (success without a run)
 *
 * This test reproduces the orphan-race deterministically on JVM (no emulator / no WorkManager
 * integration). It mocks `tryLockForUpload → 0` (simulating the row-not-READY race), calls
 * `doWork()`, and asserts the worker returned `Result.retry()` (concrete class name "Retry").
 * RED now: the worker returns `Result.success()` (class name "Success"), proven by the
 * captured `REPRO330_RESULT_CLASS=Success` log line and the ComparisonFailure
 * `expected:<[Retry]> but was:<[Success]>`. After the fix (`UploadWorker.kt:54` →
 * `Result.retry()`), the class name becomes "Retry" and this test goes GREEN.
 *
 * `androidx.work.Result` cannot be referenced by name on the JVM unit-test classpath
 * (`kotlin.Result` shadows it during resolution), but the value itself is real —
 * `work-runtime-ktx` is a testImplementation dep, so the factory `Result.success()`
 * returns a genuine `Result$Success` instance whose `javaClass.simpleName` is "Success".
 * We hold the return value as `Any` and compare the simple class name.
 *
 * The interaction assertions (`coVerify(exactly = 0)` on getById/updateStatus/upload) document the
 * symptom — the worker does no work — but they would also pass after a `Result.retry()` fix (the
 * worker still does no work in *this* attempt; it defers to WorkManager). The class-name assertion
 * is what distinguishes bug from fix and makes this a real repro, not a smoke-test.
 */
@OptIn(ExperimentalCoroutinesApi::class)
class UploadWorkerOrphanRaceReproTest {
    @Test
    fun doWork_tryLockReturnsZero_doesNoWork_andSilentlyExits_orphanRepro330() {
        val pendingUploadDao = mockk<PendingUploadDao>(relaxed = true)
        val chunkedUploader = mockk<ChunkedUploader>(relaxed = true)
        val skateLabClient = mockk<SkateLabClient>(relaxed = true)
        val appContext = mockk<Context>(relaxed = true)
        val workerParams = mockk<WorkerParameters>(relaxed = true)

        // Simulate the insert→enqueue race: the PendingUpload row is NOT found / NOT READY at the
        // moment the worker runs, so tryLockForUpload updates 0 rows.
        coEvery { pendingUploadDao.tryLockForUpload(any()) } returns 0

        val worker =
            UploadWorker(
                appContext = appContext,
                params = workerParams,
                pendingUploadDao = pendingUploadDao,
                chunkedUploader = chunkedUploader,
                skateLabClient = skateLabClient,
            )

        // Capture the Result. We cannot reference `androidx.work.Result` by name on the JVM unit
        // test classpath (it is shadowed by kotlin.Result during resolution), but the value itself
        // is real (work-runtime is a testImplementation dep, not an AGP-stubbed framework class).
        // Hold it as Any and inspect its concrete class name.
        var result: Any? = null
        runTest {
            result = worker.doWork()
        }

        // Diagnostic: prove what the worker actually returned.
        val resultClassName = result?.javaClass?.simpleName
        println("REPRO330_RESULT_CLASS=$resultClassName  toString=${result?.toString()}")

        // BUG (#330): on locked==0 the worker returns Result.success() WITHOUT doing any work —
        // it never fetches the entity (getById), never marks UPLOADING (updateStatus), never uploads.
        // WorkManager then marks the job done forever → the orphaned READY row is never processed →
        // UI hangs on "Preparing upload…".
        coVerify(exactly = 0) { pendingUploadDao.getById(any()) }
        coVerify(exactly = 0) { pendingUploadDao.updateStatus(any(), any()) }
        coVerify(exactly = 0) { chunkedUploader.upload(any(), any(), any(), any()) }

        // The real repro: the CORRECT behavior on locked==0 is Result.retry() so WorkManager
        // re-runs the worker once the PendingUpload row commits. The bug returns Result.success()
        // (class "Success") which marks the job SUCCEEDED forever → orphaned row never retried.
        // Asserting "Retry" makes this RED now (worker returns "Success") and GREEN after the fix
        // (UploadWorker.kt:54 → Result.retry()).
        assertEquals(
            "BUG #330: locked==0 must return Result.retry() so the orphaned row gets re-processed; " +
                "current code returns Result.success() and the upload hangs forever",
            "Retry",
            resultClassName,
        )
    }

    @Test
    fun doWork_tryLockReturnsOne_proceedsToFetchEntity() {
        // Baseline / contrast: when the row IS READY (tryLock=1), the worker proceeds PAST the lock
        // check and fetches the entity. This proves the lock check is the branch point — locked==0
        // must NOT silently exit; it must retry so the row (once committed) gets processed.
        val pendingUploadDao = mockk<PendingUploadDao>(relaxed = true)
        val chunkedUploader = mockk<ChunkedUploader>(relaxed = true)
        val skateLabClient = mockk<SkateLabClient>(relaxed = true)
        val appContext = mockk<Context>(relaxed = true)
        val workerParams = mockk<WorkerParameters>(relaxed = true)

        coEvery { pendingUploadDao.tryLockForUpload(any()) } returns 1
        coEvery { pendingUploadDao.getById(any()) } returns null // → worker hits `?: return Result.failure()`

        val worker =
            UploadWorker(
                appContext = appContext,
                params = workerParams,
                pendingUploadDao = pendingUploadDao,
                chunkedUploader = chunkedUploader,
                skateLabClient = skateLabClient,
            )

        runTest {
            worker.doWork()
        }

        // Worker passed the lock and fetched the entity (getById invoked) → it did NOT silently exit.
        coVerify(atLeast = 1) { pendingUploadDao.getById(any()) }
        // getById returned null → worker fails before upload; no upload attempted.
        coVerify(exactly = 0) { chunkedUploader.upload(any(), any(), any(), any()) }
    }
}
