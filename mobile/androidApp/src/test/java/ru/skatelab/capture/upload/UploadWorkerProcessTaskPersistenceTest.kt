package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.Data
import androidx.work.WorkerParameters
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import java.io.File
import kotlinx.coroutines.test.runTest
import org.junit.Test
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.api.ProcessApi
import ru.skatelab.shared.api.QueueProcessResponse
import ru.skatelab.shared.api.SessionsApi
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.models.SessionResponse

class UploadWorkerProcessTaskPersistenceTest {
    @Test
    fun doWork_persistsQueuedTaskInsteadOfCompletingUpload() =
        runTest {
            val dao = mockk<PendingUploadDao>(relaxed = true)
            val uploader = mockk<ChunkedUploader>()
            val client = mockk<SkateLabClient>()
            val sessions = mockk<SessionsApi>()
            val process = mockk<ProcessApi>()
            val video = File.createTempFile("process-task", ".mp4").apply { deleteOnExit() }
            val entity = PendingUploadEntity(id = "upload-1", videoPath = video.absolutePath)

            coEvery { dao.tryLockForUpload("upload-1") } returns 1
            coEvery { dao.getById("upload-1") } returns entity
            coEvery { uploader.upload(any(), any(), any(), any()) } returns "uploads/video.mp4"
            coEvery { client.sessions } returns sessions
            coEvery { client.process } returns process
            coEvery { sessions.create(any(), any(), any(), any()) } returns
                SessionResponse(
                    id = "session-1",
                    userId = "user-1",
                    status = "uploading",
                    createdAt = "2026-08-29T00:00:00Z",
                )
            coEvery { process.queue("uploads/video.mp4", "session-1") } returns
                QueueProcessResponse(taskId = "task-1")

            val params = mockk<WorkerParameters>(relaxed = true)
            coEvery {
                params.inputData
            } returns Data.Builder().putString("upload_id", "upload-1").build()
            val worker =
                UploadWorker(
                    appContext = mockk<Context>(relaxed = true),
                    params = params,
                    pendingUploadDao = dao,
                    chunkedUploader = uploader,
                    skateLabClient = client,
                )

            worker.doWork()

            coVerify(exactly = 1) {
                dao.updateProcessingState("upload-1", "session-1", "task-1")
            }
            coVerify(exactly = 0) { dao.updateStatus("upload-1", "COMPLETED", any()) }
        }
}
