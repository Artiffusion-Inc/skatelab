package ru.skatelab.capture.data.recording

import ru.skatelab.capture.AppLogger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.export.ImuStreamWriter
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton

@Singleton
class ImuCollector @Inject constructor(
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
    @Named("ImuIo") private val ioDispatcher: CoroutineDispatcher,
) {
    companion object {
        private const val TAG = "ImuCollector"
        // WT901 sends zero acc/gyro for ~0.5-1s after start streaming.
        // Discard samples where acc magnitude is below 1.0 m/s² (gravity component missing).
        private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
    }

    private val writers = mutableMapOf<SensorId, ImuStreamWriter>()
    private val counts = mutableMapOf<SensorId, Int>()
    private val lastSampleNs = mutableMapOf<SensorId, Long>()
    private val pendingGaps = mutableMapOf<SensorId, PendingGap>()
    private val warmedUp = mutableMapOf<SensorId, Boolean>()
    private var reconnectSeq = 0
    private var collectJob: Job? = null
    private var reconnectJob: Job? = null
    private var streamingJob: Job? = null

    fun start(scope: CoroutineScope, files: Map<SensorId, File>) {
        files.forEach { (sensorId, file) ->
            file.parentFile?.mkdirs()
            val writer = ImuStreamWriter()
            writer.open(file)
            writers[sensorId] = writer
            counts[sensorId] = 0
            lastSampleNs[sensorId] = 0L
            warmedUp[sensorId] = false
            appLogger.i(TAG, "Started IMU writer for $sensorId → ${file.absolutePath}")
        }

        collectJob = scope.launch(ioDispatcher) {
            bleRepository.imuSamples
                .filter { (id, _) -> writers.containsKey(id) }
                .collect { (sensorId, sample) ->
                    // Skip warm-up zeros: WT901 sends zero acc/gyro for ~0.5-1s
                    // after start streaming. Once we see a real sample, mark as warmed up.
                    if (warmedUp[sensorId] != true) {
                        val accMag = kotlin.math.sqrt(
                            sample.accX * sample.accX +
                            sample.accY * sample.accY +
                            sample.accZ * sample.accZ
                        )
                        if (accMag < WARMUP_MIN_ACC_MAGNITUDE) {
                            return@collect // discard warm-up zero sample
                        }
                        warmedUp[sensorId] = true
                        appLogger.i(TAG, "Sensor $sensorId warm-up complete, first real sample accMag=$accMag")
                    }

                    val writer = writers[sensorId] ?: return@collect
                    try {
                        // Write pending gap before first sample after reconnect
                        val gap: PendingGap? = pendingGaps.remove(sensorId)
                        if (gap != null && gap.lastSampleNs > 0L) {
                            writer.writeGap(gap.lastSampleNs, sample.timestampNs, gap.seq)
                            appLogger.i(TAG, "IMUGap written for $sensorId: lastNs=${gap.lastSampleNs} firstNs=${sample.timestampNs}")
                        }
                        writer.write(sample)
                        counts[sensorId] = counts.getOrDefault(sensorId, 0) + 1
                        lastSampleNs[sensorId] = sample.timestampNs
                    } catch (e: Exception) {
                        appLogger.e(TAG, "Write error for $sensorId: ${e.message}")
                    }
                }
        }

        // Watch for BLE reconnect events → insert IMUGap markers + restart streaming
        reconnectJob = scope.launch(ioDispatcher) {
            bleRepository.reconnectEvents
                .filter { writers.containsKey(it) }
                .collect { sensorId ->
                    val lastNs = lastSampleNs[sensorId] ?: 0L
                    reconnectSeq++
                    pendingGaps[sensorId] = PendingGap(lastNs, reconnectSeq)
                    warmedUp[sensorId] = false  // Sensor may send zeros again after reconnect
                    appLogger.w(TAG, "BLE reconnect gap #$reconnectSeq for $sensorId, lastNs=$lastNs")

                    // Wait for reconnection then restart streaming
                    streamingJob?.cancel()
                    streamingJob = scope.launch(ioDispatcher) {
                        try {
                            bleRepository.connectionState
                                .first { it[sensorId] == BleRepository.ConnectionState.CONNECTED }
                            bleRepository.startStreaming(sensorId).getOrElse {
                                appLogger.e(TAG, "Re-start streaming $sensorId failed: ${it.message}")
                            }
                            appLogger.i(TAG, "Streaming restarted for $sensorId after reconnect")
                        } catch (_: kotlinx.coroutines.CancellationException) {
                            // Cancelled — recording stopped
                        }
                    }
                }
        }
    }

    fun stop(): Map<SensorId, Int> {
        collectJob?.cancel()
        collectJob = null
        reconnectJob?.cancel()
        reconnectJob = null
        streamingJob?.cancel()
        streamingJob = null
        writers.forEach { (sensorId, writer) ->
            try {
                writer.close()
                appLogger.i(TAG, "Closed IMU writer for $sensorId, ${counts[sensorId]} samples")
            } catch (e: Exception) {
                appLogger.e(TAG, "Close error for $sensorId: ${e.message}")
            }
        }
        writers.clear()
        pendingGaps.clear()
        warmedUp.clear()
        val result = counts.toMap()
        counts.clear()
        return result
    }

    private data class PendingGap(val lastSampleNs: Long, val seq: Int)
}
