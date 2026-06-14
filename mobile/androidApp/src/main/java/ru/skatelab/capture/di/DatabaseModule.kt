package ru.skatelab.capture.di

import android.content.Context
import androidx.room.Room
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import ru.skatelab.capture.BuildConfig
import ru.skatelab.capture.data.db.AppDatabase
import ru.skatelab.capture.data.db.CachedSessionDao
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.upload.ChunkedUploader

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(
        @ApplicationContext context: Context,
    ): AppDatabase {
        val builder =
            Room
                .databaseBuilder(context, AppDatabase::class.java, "skatelab.db")
                .addMigrations(AppDatabase.MIGRATION_1_2, AppDatabase.MIGRATION_2_3)
        if (BuildConfig.DEBUG) {
            builder.fallbackToDestructiveMigration(true)
        }
        return builder.build()
    }

    @Provides
    fun providePendingUploadDao(db: AppDatabase): PendingUploadDao = db.pendingUploadDao()

    @Provides
    fun provideCachedSessionDao(db: AppDatabase): CachedSessionDao = db.cachedSessionDao()

    @Provides
    @Singleton
    fun provideChunkedUploader(skateLabClient: ru.skatelab.shared.api.SkateLabClient): ChunkedUploader = ChunkedUploader(skateLabClient.uploads, skateLabClient.httpClient)
}
