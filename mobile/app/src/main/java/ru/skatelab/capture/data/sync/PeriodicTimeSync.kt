package ru.skatelab.capture.data.sync

import android.os.SystemClock
import javax.inject.Inject
import javax.inject.Named
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

/**
 * Performs a one-shot time sync by reading chip time register (0x50) from each sensor.
 *
 * WT901 does NOT respond to register reads while IMU streaming is active,
 * so periodic sync during recording would always time out. Instead, this
 * reads chip time once before streaming starts and trusts that crystal drift
 * is negligible over typical recording durations (<1ms over 10 minutes).
 *
 * Call [syncAndWait] before starting IMU streaming. The returned deferred
 * completes when both sensors have been read (or failed).
 */
class PeriodicTimeSync
    @Inject
    constructor(
        private val timeSyncManager: TimeSyncManager,
        private val bleRepository: BleRepository,
        private val appLogger: AppLogger,
        @Named("clockNanos") private val clockNanos: () -> Long = { SystemClock.elapsedRealtimeNanos() },
    ) {
        companion object {
            private const val TAG = "TimeSync"
        }

        private var job: Job? = null

        /**
         * Perform a one-shot time sync for both sensors.
         * Must be called BEFORE IMU streaming starts (WT901 ignores register reads during streaming).
         */
        fun sync(scope: CoroutineScope) {
            stop()
            job =
                scope.launch {
                    val leftDeferred = async { withTimeoutOrNull(3_000L) { performRead(SensorId.LEFT) } }
                    val rightDeferred = async { withTimeoutOrNull(3_000L) { performRead(SensorId.RIGHT) } }
                    leftDeferred.await()
                    rightDeferred.await()
                }
        }

        /**
         * Suspend until the sync job completes.
         * Call after [sync] to ensure offsets are set before starting streaming.
         */
        suspend fun awaitSync() {
            job?.join()
        }

        fun stop() {
            job?.cancel()
            job = null
        }

        private suspend fun performRead(sensorId: SensorId) {
            val androidNs = clockNanos()
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
