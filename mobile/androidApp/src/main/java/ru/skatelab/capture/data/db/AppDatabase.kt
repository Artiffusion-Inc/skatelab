package ru.skatelab.capture.data.db

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

@Database(
    entities = [PendingUploadEntity::class, CachedSessionEntity::class],
    version = 3,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao

    abstract fun cachedSessionDao(): CachedSessionDao

    companion object {
        val MIGRATION_1_2 =
            object : Migration(1, 2) {
                override fun migrate(db: SupportSQLiteDatabase) {
                    db.execSQL("ALTER TABLE pending_uploads ADD COLUMN elementType TEXT DEFAULT NULL")
                }
            }

        val MIGRATION_2_3 =
            object : Migration(2, 3) {
                override fun migrate(db: SupportSQLiteDatabase) {
                    db.execSQL("ALTER TABLE pending_uploads ADD COLUMN videoKey TEXT DEFAULT NULL")
                    db.execSQL("UPDATE pending_uploads SET videoKey = r2Key WHERE r2Key IS NOT NULL")
                }
            }
    }
}
