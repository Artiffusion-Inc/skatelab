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
import javax.inject.Named
import javax.inject.Qualifier
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.BuildConfig
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
import ru.skatelab.shared.api.UsersApi
import ru.skatelab.shared.auth.AuthRepository
import ru.skatelab.shared.auth.TokenStorage
import ru.skatelab.shared.auth.createAndroidSettings

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
        fun provideSkateLabClient(tokenStorage: TokenStorage): SkateLabClient {
            val logging =
                okhttp3.logging.HttpLoggingInterceptor().apply {
                    level =
                        if (BuildConfig.DEBUG) {
                            okhttp3.logging.HttpLoggingInterceptor.Level.BODY
                        } else {
                            okhttp3.logging.HttpLoggingInterceptor.Level.NONE
                        }
                }
            return SkateLabClient(
                baseUrl = BuildConfig.API_BASE_URL,
                engine =
                    OkHttp.create {
                        config {
                            addInterceptor(logging)
                        }
                    },
                tokenStorage = tokenStorage,
            )
        }

        @Provides
        @Singleton
        fun provideTokenStorage(
            @ApplicationContext context: Context,
        ): TokenStorage = TokenStorage(createAndroidSettings(context))

        @Provides
        @Singleton
        fun provideAuthRepository(
            client: SkateLabClient,
            tokenStorage: TokenStorage,
        ): AuthRepository =
            AuthRepository(
                client.auth,
                tokenStorage,
            )

        @Provides
        @Singleton
        fun provideUsersApi(client: SkateLabClient): UsersApi = UsersApi(client.httpClient)

        @Provides
        @Singleton
        fun provideSharedAuthViewModel(
            authRepo: AuthRepository,
            usersApi: UsersApi,
            client: SkateLabClient,
        ): ru.skatelab.shared.state.AuthViewModel {
            val vm =
                ru.skatelab.shared.state
                    .AuthViewModel(authRepo, usersApi)
            client.onAuthFailure = {
                kotlinx.coroutines.GlobalScope.launch {
                    vm.onAuthFailure()
                }
            }
            return vm
        }
    }
}
