package ru.skatelab.capture.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface PendingUploadDao {
    @Query("SELECT * FROM pending_uploads WHERE status != 'COMPLETED' ORDER BY createdAt ASC")
    suspend fun getPending(): List<PendingUploadEntity>

    @Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'READY'")
    suspend fun tryLockForUpload(id: String): Int

    @Query("SELECT * FROM pending_uploads WHERE id = :id")
    suspend fun getById(id: String): PendingUploadEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: PendingUploadEntity)

    @Query("UPDATE pending_uploads SET status = :status, sessionId = :sessionId WHERE id = :id")
    suspend fun updateStatus(
        id: String,
        status: String,
        sessionId: String? = null,
    )

    @Query("UPDATE pending_uploads SET retryCount = retryCount + 1 WHERE id = :id")
    suspend fun incrementRetry(id: String)
}
