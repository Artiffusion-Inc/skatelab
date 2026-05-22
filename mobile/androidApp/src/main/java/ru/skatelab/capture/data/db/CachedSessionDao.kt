package ru.skatelab.capture.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query

@Dao
interface CachedSessionDao {
    @Query("SELECT * FROM cached_sessions ORDER BY cachedAt DESC")
    suspend fun getAll(): List<CachedSessionEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(entity: CachedSessionEntity)

    @Query("DELETE FROM cached_sessions WHERE cachedAt < :olderThan")
    suspend fun deleteOlderThan(olderThan: Long)
}
