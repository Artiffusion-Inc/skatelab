package ru.skatelab.capture

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.upload.UploadScheduler

@HiltAndroidApp
class App : Application(), Configuration.Provider {
    @Inject
    lateinit var appLogger: AppLogger

    @Inject
    lateinit var workerFactory: HiltWorkerFactory

    @Inject
    lateinit var pendingUploadDao: PendingUploadDao

    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override val workManagerConfiguration: Configuration
        get() =
            Configuration.Builder()
                .setWorkerFactory(workerFactory)
                .build()

    override fun onCreate() {
        super.onCreate()
        appLogger.open()
        appLogger.i("App", "=== APPLICATION STARTED ===")
        applicationScope.launch {
            UploadScheduler.reconcile(this@App, pendingUploadDao)
        }
    }
}
