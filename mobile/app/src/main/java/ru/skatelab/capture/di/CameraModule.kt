package ru.skatelab.capture.di

import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import ru.skatelab.capture.data.camera.CameraRepositoryImpl
import ru.skatelab.capture.domain.repository.CameraRepository

@Module
@InstallIn(SingletonComponent::class)
abstract class CameraModule {
    @Binds
    abstract fun bindCameraRepository(impl: CameraRepositoryImpl): CameraRepository
}
