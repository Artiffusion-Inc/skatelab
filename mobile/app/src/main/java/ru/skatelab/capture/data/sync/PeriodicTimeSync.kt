package ru.skatelab.capture.data.sync

import android.os.SystemClock
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject

class PeriodicTimeSync @Inject constructor(
    private val timeSyncManager: TimeSyncManager,
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
) {
    companion object {
        private const val TAG = "TimeSync"
        private const val INTERVAL_MS = 30_000L
    }

    private var job: Job? = null

    fun start(scope: CoroutineScope) {
        stop()
        job = scope.launch {
            for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                performRead(sensorId)
            }
            while (isActive) {
                delay(INTERVAL_MS)
                for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                    performRead(sensorId)
                }
            }
        }
    }

    fun stop() {
        job?.cancel()
        job = null
    }

    private suspend fun performRead(sensorId: SensorId) {
        val androidNs = SystemClock.elapsedRealtimeNanos()
        bleRepository.readChipTime(sensorId)
            .onSuccess { chipTimeMs ->
                timeSyncManager.updatePeriodicOffset(sensorId, androidNs, chipTimeMs)
                appLogger.d(TAG, "Time sync $sensorId: offset=${timeSyncManager.getOffset(sensorId)}ns")
            }
            .onFailure {
                appLogger.w(TAG, "Time sync read failed for $sensorId: ${it.message}")
            }
    }
}
