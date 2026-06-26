package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.WorkerParameters
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.shared.api.SkateLabClient

/**
 * Repro for a NEW bug — `UploadWorker` silently forces `elementType = "axel"` when
 * the PendingUpload row has `elementType == null`, so a video whose element was
 * never recorded is uploaded & analyzed as an Axel jump without any error or
 * user confirmation.
 *
 * Root cause: `UploadWorker.doWork()` (UploadWorker.kt:117):
 *
 *   val session = skateLabClient.sessions.create(
 *       elementType = entity.elementType ?: "axel",   // ← silent fallback
 *       videoKey = videoKey,
 *       imuLeftKey = imuLeftKey,
 *       imuRightKey = imuRightKey,
 *   )
 *
 * `PendingUploadEntity.elementType` is `String? = null` (PendingUploadEntity.kt:14).
 * When it is null (e.g. the capture flow failed to persist the element, or a
 * migration left the column empty), the worker does NOT fail or surface the
 * missing element — it substitutes "axel" and creates the session. The backend
 * then runs ML analysis and produces Axel-specific metrics/PRs/recommendations
 * for a video that may be a completely different element (or no jump at all).
 *
 * Consequences:
 *   - Wrong element classification → metrics are computed against the wrong
 *     reference ranges / metric registry (element_types filter), PRs are filed
 *     under "axel", trend/diagnostics are polluted.
 *   - The user is never told the element was unknown; they see an "Axel"
 *     analysis they did not request. Silent data corruption of the user's
 *     training history.
 *   - Related to #331 (i18n hardcoded element) — "axel" is also a hardcoded
 *     English/ISU key, compounding the i18n gap, but the core defect here is
 *     the silent fallback, not the string itself.
 *
 * The existing `UploadWorkerOrphanRaceReproTest` (#330) covers the locked==0
 * orphan path; it does NOT cover the elementType-null path (its entities either
 * don't reach create or have a real element). So the silent-axel fallback never
 * surfaces in CI.
 *
 * Repro: build a PendingUploadEntity with `elementType = null`, a real temp
 * video file, mock the DAO lock/getById/updateVideoKey and ChunkedUploader to
 * succeed; then assert `sessions.create` is NOT called with `elementType =
 * "axel"`. RED now: it IS called with "axel" (the fallback fires). After the
 * fix (fail / surface an error when elementType is null instead of defaulting)
 * → `create` is not called with "axel" (worker fails before creating a session,
 * or surfaces the missing element).
 *
 * No production data mutated: JVM unit test, mocked deps, a throwaway temp file.
 */

@OptIn(ExperimentalCoroutinesApi::class)
class UploadWorkerSilentAxelFallbackReproTest {
    @Test
    fun doWork_nullElementType_mustNotSilentlyCreateAxelSession_repro() {
        val pendingUploadDao = mockk<PendingUploadDao>(relaxed = true)
        val chunkedUploader = mockk<ChunkedUploader>(relaxed = true)
        val skateLabClient = mockk<SkateLabClient>(relaxed = true)
        val sessions = mockk<ru.skatelab.shared.api.SessionsApi>(relaxed = true)
        val appContext = mockk<Context>(relaxed = true)
        val workerParams = mockk<WorkerParameters>(relaxed = true)

        // Lock succeeds (row is READY) and the entity exists with a real video file
        // but NO element type — the defect condition.
        coEvery { pendingUploadDao.tryLockForUpload(any()) } returns 1

        val tmpVideo = File.createTempFile("repro_axel", ".mp4").apply { writeBytes(ByteArray(16)) }
        tmpVideo.deleteOnExit()

        val entity = ru.skatelab.capture.data.db.PendingUploadEntity(
            id = "upload-1",
            videoPath = tmpVideo.absolutePath,
            elementType = null, // ← the defect: element never recorded
        )
        coEvery { pendingUploadDao.getById(any()) } returns entity
        coEvery { chunkedUploader.upload(any(), any(), any(), any()) } returns "uploads/x/y.mp4"
        coEvery { skateLabClient.sessions } returns sessions
        coEvery {
            sessions.create(elementType = any(), videoKey = any(), imuLeftKey = any(), imuRightKey = any())
        } returns mockk(relaxed = true)

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

        // CONTRACT: the worker must NOT silently fabricate elementType="axel" for a
        // row whose element is null. RED now: sessions.create IS invoked with
        // elementType="axel" (the `?: "axel"` fallback). After the fix (fail /
        // surface the missing element) → create is not called with "axel".
        coVerify(exactly = 0) {
            sessions.create(
                elementType = eq("axel"),
                videoKey = any(),
                imuLeftKey = any(),
                imuRightKey = any(),
            )
        }

        // Stronger contract: create must not be called at all when the element is
        // unknown — the worker should fail / surface the error instead of
        // inventing an element. (If the team prefers a different default, the
        // primary RED above still pins that "axel" specifically must not leak.)
        coVerify(exactly = 0) {
            sessions.create(
                elementType = any(),
                videoKey = any(),
                imuLeftKey = any(),
                imuRightKey = any(),
            )
        }
    }
}