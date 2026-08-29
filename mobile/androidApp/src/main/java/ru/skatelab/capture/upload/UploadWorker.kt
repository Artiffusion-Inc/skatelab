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
import java.io.IOException
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
            val initialEntity = pendingUploadDao.getById(uploadId) ?: return Result.failure()

            // A persisted task is authoritative: never queue a second task after restart.
            if (initialEntity.status == "PROCESSING" && initialEntity.processTaskId != null) {
                return observeExistingTask(initialEntity)
            }

            // Atomic lock: only proceed if status is READY (prevents duplicate workers).
            val locked = pendingUploadDao.tryLockForUpload(uploadId)
            if (locked == 0) {
                val currentEntity = pendingUploadDao.getById(uploadId)
                return if (currentEntity?.status == "PROCESSING" && currentEntity.processTaskId != null) {
                    observeExistingTask(currentEntity)
                } else {
                    Result.success()
                }
            }

            val entity = pendingUploadDao.getById(uploadId) ?: return Result.failure()
            if (entity.processTaskId != null) {
                return observeExistingTask(entity)
            }

            return try {
                // Reuse a key persisted before process death instead of uploading again.
                val videoKey =
                    entity.videoKey ?: run {
                        val videoFile = File(entity.videoPath)
                        if (!videoFile.exists()) {
                            pendingUploadDao.updateStatus(entity.id, "FAILED")
                            return Result.failure()
                        }

                        val uploadedKey =
                            chunkedUploader.upload(
                                file = videoFile,
                                fileName = videoFile.name,
                                contentType = "video/mp4",
                                onProgress = { uploaded, total ->
                                    val percent = (uploaded.toFloat() / total).coerceIn(0f, 1f)
                                    setProgress(workDataOf(KEY_UPLOAD_ID to uploadId, KEY_PROGRESS to percent))
                                },
                            )
                        pendingUploadDao.updateVideoKey(entity.id, uploadedKey)
                        uploadedKey
                    }

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
                var manifestKey: String? = null
                entity.manifestPath?.let { path ->
                    val file = File(path)
                    if (file.exists()) {
                        manifestKey = uploadPresigned(file, "application/json")
                    }
                }

                // Reuse a session created before process death, if one was persisted.
                val sessionId =
                    entity.sessionId ?: run {
                        val session =
                            skateLabClient.sessions.create(
                                elementType = entity.elementType,
                                videoKey = videoKey,
                                imuLeftKey = imuLeftKey,
                                imuRightKey = imuRightKey,
                                manifestKey = manifestKey,
                            )
                        // Persist before queueing so a retry cannot create another session.
                        pendingUploadDao.updateStatus(entity.id, "UPLOADING", session.id)
                        session.id
                    }

                // Step 5: Enqueue once and persist the task so UI can resume its SSE stream.
                val task =
                    skateLabClient.process.queue(
                        videoKey = videoKey,
                        sessionId = sessionId,
                    )
                pendingUploadDao.updateProcessingState(entity.id, sessionId, task.taskId)
                Result.success()
            } catch (e: Exception) {
                // Network/offline errors: surface immediately to the user as FAILED.
                // Non-network transient errors (e.g. 503): retry up to 3 times,
                // but first reset status to READY so tryLockForUpload can lock again.
                if (e is IOException) {
                    pendingUploadDao.updateStatus(entity.id, "NETWORK_ERROR")
                    Result.failure()
                } else {
                    pendingUploadDao.incrementRetry(entity.id)
                    val currentEntity = pendingUploadDao.getById(uploadId)
                    if ((currentEntity?.retryCount ?: 0) >= 3) {
                        pendingUploadDao.updateStatus(entity.id, "FAILED")
                        Result.failure()
                    } else {
                        // Reset to READY so the next worker run can lock this row.
                        pendingUploadDao.updateStatus(entity.id, "READY")
                        Result.retry()
                    }
                }
            }
        }

        private suspend fun observeExistingTask(entity: ru.skatelab.capture.data.db.PendingUploadEntity): Result {
            return try {
                val status = skateLabClient.process.status(entity.processTaskId!!).status.lowercase()
                when (status) {
                    "completed" -> pendingUploadDao.updateStatus(entity.id, "COMPLETED", entity.sessionId)
                    "failed", "cancelled" -> pendingUploadDao.updateStatus(entity.id, "FAILED", entity.sessionId)
                }
                Result.success()
            } catch (e: Exception) {
                // Keep PROCESSING intact; retrying observation must not re-enter upload/queue.
                Result.retry()
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
