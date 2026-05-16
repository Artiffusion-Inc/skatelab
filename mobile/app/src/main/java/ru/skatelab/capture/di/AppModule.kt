package ru.skatelab.capture.di

import android.os.SystemClock
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Named
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.ble.BleRepositoryImpl
import ru.skatelab.capture.data.export.ManifestBuilder
import ru.skatelab.capture.data.export.ZipExporter
import ru.skatelab.capture.data.recording.ImuCollector
import ru.skatelab.capture.data.repository.SessionRepositoryImpl
import ru.skatelab.capture.data.sync.TimeSynchronizerImpl
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import ru.skatelab.capture.domain.service.ImuCollector as ImuCollectorInterface
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.service.ManifestWriter
import ru.skatelab.capture.domain.service.SessionExporter
import ru.skatelab.capture.domain.service.TimeSynchronizer

@Module
@InstallIn(SingletonComponent::class)
abstract class AppModule {
    @Binds
    @Singleton
    abstract fun bindBleRepository(impl: BleRepositoryImpl): BleRepository

    @Binds
    @Singleton
    abstract fun bindSessionRepository(impl: SessionRepositoryImpl): SessionRepository

    @Binds
    @Singleton
    abstract fun bindSessionExporter(impl: ZipExporter): SessionExporter

    @Binds
    @Singleton
    abstract fun bindManifestWriter(impl: ManifestBuilder): ManifestWriter

    @Binds
    @Singleton
    abstract fun bindLogger(impl: AppLogger): Logger

    @Binds
    @Singleton
    abstract fun bindImuCollector(impl: ImuCollector): ImuCollectorInterface

    @Binds
    @Singleton
    abstract fun bindTimeSynchronizer(impl: TimeSynchronizerImpl): TimeSynchronizer

    companion object {
        @dagger.Provides
        @Named("Io")
        fun provideIoDispatcher(): CoroutineDispatcher = Dispatchers.IO

        @dagger.Provides
        @Named("ImuIo")
        @Singleton
        fun provideImuIoDispatcher(): CoroutineDispatcher = Dispatchers.IO.limitedParallelism(4)

        @dagger.Provides
        @Named("clockNanos")
        fun provideClockNanos(): () -> Long = { SystemClock.elapsedRealtimeNanos() }
    }
}
