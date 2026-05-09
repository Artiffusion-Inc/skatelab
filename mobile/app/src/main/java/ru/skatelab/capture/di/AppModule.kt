package ru.skatelab.capture.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import ru.skatelab.capture.data.ble.BleRepositoryImpl
import ru.skatelab.capture.data.camera.Camera2Recorder
import ru.skatelab.capture.data.export.ZipExporter
import ru.skatelab.capture.data.repository.SessionRepositoryImpl
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.domain.repository.SessionRepository
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
abstract class AppModule {

    @Binds
    @Singleton
    abstract fun bindBleRepository(impl: BleRepositoryImpl): BleRepository

    @Binds
    @Singleton
    abstract fun bindCameraRepository(impl: Camera2Recorder): CameraRepository

    @Binds
    @Singleton
    abstract fun bindSessionRepository(impl: SessionRepositoryImpl): SessionRepository

    companion object {
        @dagger.Provides
        @Singleton
        fun provideZipExporter(): ZipExporter = ZipExporter()
    }
}
