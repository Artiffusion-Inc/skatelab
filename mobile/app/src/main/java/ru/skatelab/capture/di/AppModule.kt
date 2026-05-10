package ru.skatelab.capture.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.asCoroutineDispatcher
import ru.skatelab.capture.data.ble.BleRepositoryImpl
import ru.skatelab.capture.data.export.ZipExporter
import ru.skatelab.capture.data.repository.SessionRepositoryImpl
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import android.os.SystemClock
import java.util.concurrent.Executors
import javax.inject.Named
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class AppModule {

    @Binds
    @Singleton
    abstract fun bindBleRepository(impl: BleRepositoryImpl): BleRepository

    @Binds
    @Singleton
    abstract fun bindSessionRepository(impl: SessionRepositoryImpl): SessionRepository

    companion object {
        @dagger.Provides
        @Singleton
        fun provideZipExporter(): ZipExporter = ZipExporter()

        @dagger.Provides
        @Named("Io")
        fun provideIoDispatcher(): CoroutineDispatcher = Dispatchers.IO

        @dagger.Provides
        @Named("ImuIo")
        @Singleton
        fun provideImuIoDispatcher(): CoroutineDispatcher =
            Executors.newSingleThreadExecutor().asCoroutineDispatcher()

        @dagger.Provides
        @Named("clockNanos")
        fun provideClockNanos(): () -> Long = { SystemClock.elapsedRealtimeNanos() }
    }
}
