package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.Data
import androidx.work.WorkerParameters
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.capture.data.db.FakePendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.api.ProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.api.TaskStatusResponse

class UploadRecoveryTest {
    @Test
    fun staleUploading_requeuesWithoutDroppingPersistedKeys() =
        runTest {
            val dao = FakePendingUploadDao()
            dao.insert(
                PendingUploadEntity(
                    id = "upload-1",
                    videoPath = "/tmp/video.mp4",
                    status = "UPLOADING",
                    videoKey = "videos/existing.mp4",
                    sessionId = "session-1",
                ),
            )

            assertEquals(1, dao.resetStaleUploads())

            val recovered = dao.getById("upload-1")
            assertEquals("READY", recovered?.status)
            assertEquals("videos/existing.mp4", recovered?.videoKey)
            assertEquals("session-1", recovered?.sessionId)
        }

    @Test
    fun processingWithTaskId_observesExistingTaskWithoutQueueing() =
        runTest {
            val dao = mockk<PendingUploadDao>(relaxed = true)
            val process = mockk<ProcessApi>()
            val client = mockk<SkateLabClient>()
            val entity =
                PendingUploadEntity(
                    id = "upload-1",
                    videoPath = "/tmp/video.mp4",
                    status = "PROCESSING",
                    videoKey = "videos/existing.mp4",
                    sessionId = "session-1",
                    processTaskId = "task-1",
                )
            coEvery { dao.getById("upload-1") } returns entity
            coEvery { client.process } returns process
            coEvery { process.status("task-1") } returns
                TaskStatusResponse(
                    taskId = "task-1",
                    status = "running",
                    progress = 0.5f,
                    message = "Processing",
                )

            val worker =
                UploadWorker(
                    appContext = mockk<Context>(relaxed = true),
                    params = workerParams("upload-1"),
                    pendingUploadDao = dao,
                    chunkedUploader = mockk(relaxed = true),
                    skateLabClient = client,
                )

            val result = worker.doWork()

            assertTrue(result is androidx.work.ListenableWorker.Result.Success)
            coVerify(exactly = 1) { process.status("task-1") }
            coVerify(exactly = 0) { process.queue(any(), any()) }
            coVerify(exactly = 0) { dao.tryLockForUpload(any()) }
        }

    @Test
    fun readyWithPersistedVideoAndSession_reusesKeysAndQueuesOnce() =
        runTest {
            val dao = mockk<PendingUploadDao>(relaxed = true)
            val process = mockk<ProcessApi>()
            val client = mockk<SkateLabClient>()
            val entity =
                PendingUploadEntity(
                    id = "upload-1",
                    videoPath = "/tmp/video.mp4",
                    status = "READY",
                    videoKey = "videos/existing.mp4",
                    sessionId = "session-1",
                )
            coEvery { dao.getById("upload-1") } returns entity
            coEvery { dao.tryLockForUpload("upload-1") } returns 1
            coEvery { client.process } returns process
            coEvery { process.queue("videos/existing.mp4", "session-1") } returns
                QueueProcessResponse(taskId = "task-1")

            val worker =
                UploadWorker(
                    appContext = mockk<Context>(relaxed = true),
                    params = workerParams("upload-1"),
                    pendingUploadDao = dao,
                    chunkedUploader = mockk(relaxed = true),
                    skateLabClient = client,
                )

            worker.doWork()

            coVerify(exactly = 0) { client.sessions.create(any(), any(), any(), any(), any(), any()) }
            coVerify(exactly = 1) { process.queue("videos/existing.mp4", "session-1") }
            coVerify(exactly = 1) { dao.updateProcessingState("upload-1", "session-1", "task-1") }
        }

    private fun workerParams(uploadId: String): WorkerParameters {
        val params = mockk<WorkerParameters>(relaxed = true)
        coEvery { params.inputData } returns Data.Builder().putString(UploadWorker.KEY_UPLOAD_ID, uploadId).build()
        return params
    }
}
