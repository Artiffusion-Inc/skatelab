package ru.skatelab.capture.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "pending_uploads")
// Status values: READY, UPLOADING, PROCESSING, COMPLETED, FAILED
data class PendingUploadEntity(
    @PrimaryKey val id: String,
    val videoPath: String,
    val imuLeftPath: String? = null,
    val imuRightPath: String? = null,
    val manifestPath: String? = null,
    val elementType: String? = null,
    val status: String = "READY",
    val uploadId: String? = null,
    val r2Key: String? = null,
    val sessionId: String? = null,
    val retryCount: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
)
