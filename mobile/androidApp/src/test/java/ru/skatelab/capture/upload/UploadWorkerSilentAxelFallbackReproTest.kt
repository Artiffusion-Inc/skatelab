package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.WorkerParameters
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.runTest
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.shared.api.SkateLabClient

/**
 * Repro for #355 — UploadWorker silently forces `elementType = "axel"` when
 * the PendingUpload row has `elementType == null`. Under the AUTO-DETECT
 * direction, the worker must pass `null` through to the backend so the ML
 * pipeline can auto-detect the element (TAS classifier → ISU code remap).
 *
 * Root cause (before fix): UploadWorker.kt:112
 *   elementType = entity.elementType ?: "axel"   // ← silent fallback
 *
 * Fixed contract: when entity.elementType is null, the worker MUST call
 * sessions.create with elementType = null (not "axel", not omitted).
 * The backend accepts nullable element_type; the ML pipeline fills it in
 * after analysis via compose_isu_element_type.
 *
 * No production data mutated: JVM unit test, mocked deps, a throwaway temp file.
 */

@OptIn(ExperimentalCoroutinesApi::class)
class UploadWorkerSilentAxelFallbackReproTest {
    @Test
    fun doWork_nullElementType_mustCreateSessionWithNull_notAxel() {
        val pendingUploadDao = mockk<PendingUploadDao>(relaxed = true)
        val chunkedUploader = mockk<ChunkedUploader>(relaxed = true)
        val skateLabClient = mockk<SkateLabClient>(relaxed = true)
        val sessions = mockk<ru.skatelab.shared.api.SessionsApi>(relaxed = true)
        val appContext = mockk<Context>(relaxed = true)
        val workerParams = mockk<WorkerParameters>(relaxed = true)

        // Lock succeeds (row is READY) and the entity exists with a real video file
        // but NO element type — the auto-detect condition.
        coEvery { pendingUploadDao.tryLockForUpload(any()) } returns 1

        val tmpVideo = File.createTempFile("repro_axel", ".mp4").apply { writeBytes(ByteArray(16)) }
        tmpVideo.deleteOnExit()

        val entity =
            ru.skatelab.capture.data.db.PendingUploadEntity(
                id = "upload-1",
                videoPath = tmpVideo.absolutePath,
                elementType = null,
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

        // CONTRACT (auto-detect):
        //   1. sessions.create IS called with elementType = null
        //   2. sessions.create is NEVER called with elementType = "axel"
        coVerify(exactly = 1) {
            sessions.create(
                elementType = null,
                videoKey = any(),
                imuLeftKey = any(),
                imuRightKey = any(),
            )
        }
        coVerify(exactly = 0) {
            sessions.create(
                elementType = "axel",
                videoKey = any(),
                imuLeftKey = any(),
                imuRightKey = any(),
            )
        }
    }
}
