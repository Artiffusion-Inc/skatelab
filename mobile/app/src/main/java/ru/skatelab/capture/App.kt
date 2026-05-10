package ru.skatelab.capture

import android.app.Application
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class App : Application() {

    @Inject
    lateinit var appLogger: AppLogger

    override fun onCreate() {
        super.onCreate()
        appLogger.open()
        appLogger.i("App", "=== APPLICATION STARTED ===")
    }
}
