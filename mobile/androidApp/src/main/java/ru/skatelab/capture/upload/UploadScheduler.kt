package ru.skatelab.capture.upload

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit
import ru.skatelab.capture.data.db.PendingUploadDao

/**
 * Enqueues [UploadWorker] with proper network constraints and exponential backoff.
 * Should be called after a PendingUploadEntity is saved to Room.
 */
object UploadScheduler {
    suspend fun reconcile(
        context: Context,
        pendingUploadDao: PendingUploadDao,
    ) {
        pendingUploadDao.resetStaleUploads()
        pendingUploadDao.getPending()
            .filter { entity ->
                entity.status == "READY" ||
                    (entity.status == "PROCESSING" && entity.processTaskId != null)
            }.forEach { entity ->
                enqueue(context, entity.id)
            }
    }

    fun enqueue(
        context: Context,
        uploadId: String,
        policy: ExistingWorkPolicy = ExistingWorkPolicy.KEEP,
    ) {
        val constraints =
            Constraints
                .Builder()
                .setRequiresBatteryNotLow(true)
                .build()

        val workRequest =
            OneTimeWorkRequestBuilder<UploadWorker>()
                .setInputData(UploadWorker.inputData(uploadId))
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()

        WorkManager
            .getInstance(context)
            .enqueueUniqueWork(
                "upload-$uploadId",
                policy,
                workRequest,
            )
    }
}
