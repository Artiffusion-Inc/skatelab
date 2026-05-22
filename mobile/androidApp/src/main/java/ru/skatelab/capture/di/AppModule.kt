package ru.skatelab.capture.di

import android.content.Context
import android.os.SystemClock
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import io.ktor.client.engine.okhttp.*
import io.ktor.client.plugins.auth.providers.BearerAuthProvider
import javax.inject.Named
import javax.inject.Qualifier
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.ble.KableBleRepository
import ru.skatelab.capture.data.ble.NoOpBleRepository
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
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.TokenStorage

@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class NoOpBle

@Module
@InstallIn(SingletonComponent::class)
abstract class AppModule {
    @Binds
    @Singleton
    abstract fun bindBleRepository(impl: KableBleRepository): BleRepository

    @Binds
    @Singleton
    @NoOpBle
    abstract fun bindNoOpBleRepository(impl: NoOpBleRepository): BleRepository

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
        @Provides
        @Named("Io")
        fun provideIoDispatcher(): CoroutineDispatcher = Dispatchers.IO

        @Provides
        @Named("ImuIo")
        @Singleton
        fun provideImuIoDispatcher(): CoroutineDispatcher = Dispatchers.IO.limitedParallelism(4)

        @Provides
        @Named("clockNanos")
        fun provideClockNanos(): () -> Long = { SystemClock.elapsedRealtimeNanos() }

        @Provides
        @Singleton
        fun provideSkateLabClient(tokenStorage: TokenStorage): SkateLabClient =
            SkateLabClient(
                baseUrl = "https://api.skatelab.ru/api/v1",
                engine = OkHttp.create(),
                tokenStorage = tokenStorage,
            )

        @Provides
        @Singleton
        fun provideTokenStorage(
            @ApplicationContext context: Context,
        ): TokenStorage = TokenStorage().also { it.init(context) }

        @Provides
        @Singleton
        fun provideAuthRepository(
            client: SkateLabClient,
            tokenStorage: TokenStorage,
        ): AuthRepository =
            AuthRepository(
                client.auth,
                tokenStorage,
            ) { client.httpClient.authProvider<BearerAuthProvider>()?.clearToken() }
    }
}
