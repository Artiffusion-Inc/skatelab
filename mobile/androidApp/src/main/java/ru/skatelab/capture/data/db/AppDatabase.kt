package ru.skatelab.capture.data.db

import androidx.room.Database
import androidx.room.RoomDatabase

@Database(
    entities = [PendingUploadEntity::class, CachedSessionEntity::class],
    version = 1,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao

    abstract fun cachedSessionDao(): CachedSessionDao
}
