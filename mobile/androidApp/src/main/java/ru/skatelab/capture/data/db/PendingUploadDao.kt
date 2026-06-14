package ru.skatelab.capture.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface PendingUploadDao {
    @Query("SELECT * FROM pending_uploads WHERE status != 'COMPLETED' ORDER BY createdAt ASC")
    suspend fun getPending(): List<PendingUploadEntity>

    @Query("UPDATE pending_uploads SET status = 'UPLOADING' WHERE id = :id AND status = 'READY'")
    suspend fun tryLockForUpload(id: String): Int

    @Query("SELECT * FROM pending_uploads WHERE id = :id")
    suspend fun getById(id: String): PendingUploadEntity?

    @Query("SELECT * FROM pending_uploads WHERE id = :id LIMIT 1")
    fun getByIdFlow(id: String): Flow<PendingUploadEntity?>

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

    @Query("SELECT * FROM pending_uploads ORDER BY createdAt DESC")
    fun getAll(): Flow<List<PendingUploadEntity>>

    @Query("SELECT COUNT(*) FROM pending_uploads WHERE status IN ('READY', 'UPLOADING', 'PROCESSING')")
    fun countPending(): Flow<Int>

    @Query("UPDATE pending_uploads SET status = 'READY', retryCount = 0 WHERE id = :id")
    suspend fun resetForRetry(id: String)

    @Query("DELETE FROM pending_uploads WHERE id = :id")
    suspend fun delete(id: String)

    @Query("UPDATE pending_uploads SET videoKey = :videoKey WHERE id = :id")
    suspend fun updateVideoKey(
        id: String,
        videoKey: String,
    )
}
