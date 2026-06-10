package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import java.io.File
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.shared.api.SkateLabClient

/**
 * WorkManager CoroutineWorker that uploads a captured session:
 * 1. Upload video via ChunkedUploader (multipart to R2)
 * 2. Upload IMU files via presigned PUT (left + right, if present)
 * 3. Upload manifest via presigned PUT (if present)
 * 4. Create session on backend
 * 5. Enqueue ML processing
 * 6. Update Room status throughout
 *
 * Input data must contain KEY_UPLOAD_ID (PendingUploadEntity.id).
 * Max 3 retries with exponential backoff.
 *
 * Uses @AssistedInject for Hilt WorkerFactory integration.
 * Requires App to implement Configuration.Provider with HiltWorkerFactory.
 */
class UploadWorker
    @AssistedInject
    constructor(
        @Assisted appContext: Context,
        @Assisted params: WorkerParameters,
        private val pendingUploadDao: PendingUploadDao,
        private val chunkedUploader: ChunkedUploader,
        private val skateLabClient: SkateLabClient,
    ) : CoroutineWorker(appContext, params) {
        companion object {
            const val KEY_UPLOAD_ID = "upload_id"
            const val KEY_PROGRESS = "progress"
            private const val TAG = "UploadWorker"

            fun inputData(uploadId: String): Data = workDataOf(KEY_UPLOAD_ID to uploadId)
        }

        override suspend fun doWork(): Result {
            val uploadId = inputData.getString(KEY_UPLOAD_ID) ?: return Result.failure()

            // Atomic lock: only proceed if status is READY (prevents duplicate workers)
            val locked = pendingUploadDao.tryLockForUpload(uploadId)
            if (locked == 0) return Result.success() // Another worker already processing

            val entity = pendingUploadDao.getById(uploadId) ?: return Result.failure()

            // Mark as UPLOADING before starting upload
            pendingUploadDao.updateStatus(entity.id, "UPLOADING")

            return try {
                // Step 1: Upload video via chunked uploader
                val videoFile = File(entity.videoPath)
                if (!videoFile.exists()) {
                    pendingUploadDao.updateStatus(entity.id, "FAILED")
                    return Result.failure()
                }

                val videoKey =
                    chunkedUploader.upload(
                        file = videoFile,
                        fileName = videoFile.name,
                        contentType = "video/mp4",
                        onProgress = { uploaded, total ->
                            val percent = (uploaded.toFloat() / total).coerceIn(0f, 1f)
                            setProgress(workDataOf(KEY_UPLOAD_ID to uploadId, KEY_PROGRESS to percent))
                        },
                    )

                // Save video key so ProcessingScreen can pass it to SSE
                pendingUploadDao.updateVideoKey(entity.id, videoKey)

                // Step 2: Upload IMU files via presigned PUT (left, right)
                var imuLeftKey: String? = null
                var imuRightKey: String? = null

                entity.imuLeftPath?.let { path ->
                    val file = File(path)
                    if (file.exists()) {
                        imuLeftKey = uploadPresigned(file, "application/octet-stream")
                    }
                }

                entity.imuRightPath?.let { path ->
                    val file = File(path)
                    if (file.exists()) {
                        imuRightKey = uploadPresigned(file, "application/octet-stream")
                    }
                }

                // Step 3: Upload manifest via presigned PUT (if present)
                entity.manifestPath?.let { path ->
                    val file = File(path)
                    if (file.exists()) {
                        uploadPresigned(file, "application/json")
                    }
                }

                // Step 4: Create session on backend
                val session =
                    skateLabClient.sessions.create(
                        elementType = entity.elementType ?: "axel",
                        videoKey = videoKey,
                        imuLeftKey = imuLeftKey,
                        imuRightKey = imuRightKey,
                    )

                // Mark PROCESSING with sessionId so ProcessingScreen can start SSE
                pendingUploadDao.updateStatus(entity.id, "PROCESSING", session.id)

                // Step 5: Enqueue ML processing
                skateLabClient.process.queue(
                    videoKey = videoKey,
                    sessionId = session.id,
                )

                // Step 6: Mark completed with session ID
                pendingUploadDao.updateStatus(entity.id, "COMPLETED", session.id)
                Result.success()
            } catch (e: Exception) {
                pendingUploadDao.incrementRetry(entity.id)
                val currentEntity = pendingUploadDao.getById(uploadId)
                if ((currentEntity?.retryCount ?: 0) >= 3) {
                    pendingUploadDao.updateStatus(entity.id, "FAILED")
                    Result.failure()
                } else {
                    Result.retry()
                }
            }
        }

        private suspend fun uploadPresigned(
            file: File,
            contentType: String,
        ): String {
            val presign = skateLabClient.uploads.presign(file.name, contentType)
            val response: io.ktor.client.statement.HttpResponse =
                skateLabClient.httpClient.put(presign.url) {
                    headers.append(HttpHeaders.ContentType, contentType)
                    setBody(file.readBytes())
                }
            if (!response.status.isSuccess()) {
                throw UploadException("Presigned upload failed for ${file.name}: ${response.status.value}")
            }
            return presign.key
        }
    }
