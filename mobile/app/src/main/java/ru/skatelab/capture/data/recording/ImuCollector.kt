package ru.skatelab.capture.data.recording

import java.io.File
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.export.ImuStreamWriter
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.service.ImuCollector as ImuCollectorInterface

@Singleton
class ImuCollector
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val appLogger: AppLogger,
        @Named("ImuIo") private val ioDispatcher: CoroutineDispatcher,
    ) : ImuCollectorInterface {
        companion object {
            private const val TAG = "ImuCollector"
            private const val FLUSH_INTERVAL_MS = 2_000L

            // WT901 sends zero acc/gyro for ~0.5-1s after start streaming.
            private const val WARMUP_MIN_ACC_MAGNITUDE = 1.0f
        }

        private val writers = ConcurrentHashMap<SensorId, ImuStreamWriter>()
        private val counts = ConcurrentHashMap<SensorId, AtomicInteger>()
        private val lastSampleNs = ConcurrentHashMap<SensorId, Long>()
        private val pendingGaps = ConcurrentHashMap<SensorId, PendingGap>()
        private val warmedUp = ConcurrentHashMap<SensorId, Boolean>()
        private val reconnectSeq = AtomicInteger(0)

        private val collectJobs = mutableMapOf<SensorId, Job>()
        private var reconnectJob: Job? = null
        private var flushJob: Job? = null
        private val streamingJobs = ConcurrentHashMap<SensorId, Job>()

        override fun start(
            scope: CoroutineScope,
            files: Map<SensorId, File>,
        ) {
            files.forEach { (sensorId, file) ->
                file.parentFile?.mkdirs()
                val writer = ImuStreamWriter()
                writer.open(file)
                writers[sensorId] = writer
                counts[sensorId] = AtomicInteger(0)
                lastSampleNs[sensorId] = 0L
                warmedUp[sensorId] = false
                appLogger.i(TAG, "Started IMU writer for $sensorId → ${file.absolutePath}")
            }

            // Per-sensor collection jobs — eliminates head-of-line blocking between sensors
            files.keys.forEach { sensorId ->
                collectJobs[sensorId] =
                    scope.launch(ioDispatcher) {
                        bleRepository.imuSamples
                            .filter { (id, _) -> id == sensorId }
                            .collect { (_, sample) ->
                                handleSample(sensorId, sample)
                            }
                    }
            }

            // Watch for BLE reconnect events → insert IMUGap markers + restart streaming
            reconnectJob =
                scope.launch(ioDispatcher) {
                    bleRepository.reconnectEvents
                        .filter { writers.containsKey(it) }
                        .collect { sensorId ->
                            val lastNs = lastSampleNs[sensorId] ?: 0L
                            val seq = reconnectSeq.incrementAndGet()
                            pendingGaps[sensorId] = PendingGap(lastNs, seq)
                            warmedUp[sensorId] = false
                            appLogger.w(TAG, "BLE reconnect gap #$seq for $sensorId, lastNs=$lastNs")

                            streamingJobs[sensorId]?.cancel()
                            streamingJobs[sensorId] =
                                scope.launch(ioDispatcher) {
                                    try {
                                        bleRepository.connectionState
                                            .first { it[sensorId] == BleRepository.ConnectionState.CONNECTED }
                                        bleRepository.startStreaming(sensorId).getOrElse {
                                            appLogger.e(TAG, "Re-start streaming $sensorId failed: ${it.message}")
                                        }
                                        appLogger.i(TAG, "Streaming restarted for $sensorId after reconnect")
                                    } catch (_: CancellationException) {
                                        // Cancelled — recording stopped
                                    }
                                }
                        }
                }

            // Periodic flush to reduce data loss on crash
            flushJob =
                scope.launch(ioDispatcher) {
                    while (isActive) {
                        delay(FLUSH_INTERVAL_MS)
                        writers.values.forEach { w ->
                            try {
                                w.flush()
                            } catch (_: Exception) {
                                // best effort
                            }
                        }
                    }
                }
        }

        private fun handleSample(
            sensorId: SensorId,
            sample: ImuSample,
        ) {
            // Skip warm-up zeros
            if (warmedUp[sensorId] != true) {
                val accMag =
                    kotlin.math.sqrt(
                        sample.accX * sample.accX +
                            sample.accY * sample.accY +
                            sample.accZ * sample.accZ,
                    )
                if (accMag < WARMUP_MIN_ACC_MAGNITUDE) {
                    return // discard warm-up zero sample
                }
                warmedUp[sensorId] = true
                appLogger.i(TAG, "Sensor $sensorId warm-up complete, first real sample accMag=$accMag")
            }

            val writer = writers[sensorId] ?: return
            try {
                val gap = pendingGaps.remove(sensorId)
                if (gap != null && gap.lastSampleNs > 0L) {
                    writer.writeGap(gap.lastSampleNs, sample.timestampNs, gap.seq)
                    appLogger.i(TAG, "IMUGap written for $sensorId: lastNs=${gap.lastSampleNs} firstNs=${sample.timestampNs}")
                }
                writer.write(sample)
                counts[sensorId]?.incrementAndGet()
                lastSampleNs[sensorId] = sample.timestampNs
            } catch (e: Exception) {
                appLogger.e(TAG, "Write error for $sensorId: ${e.message}")
            }
        }

        override fun stop(): Map<SensorId, Int> {
            collectJobs.values.forEach { it.cancel() }
            collectJobs.clear()
            reconnectJob?.cancel()
            reconnectJob = null
            streamingJobs.values.forEach { it.cancel() }
            streamingJobs.clear()
            flushJob?.cancel()
            flushJob = null

            writers.forEach { (sensorId, writer) ->
                try {
                    writer.close()
                    appLogger.i(TAG, "Closed IMU writer for $sensorId, ${counts[sensorId]?.get() ?: 0} samples")
                } catch (e: Exception) {
                    appLogger.e(TAG, "Close error for $sensorId: ${e.message}")
                }
            }
            writers.clear()
            pendingGaps.clear()
            warmedUp.clear()
            val result = counts.mapValues { it.value.get() }
            counts.clear()
            return result
        }

        private data class PendingGap(val lastSampleNs: Long, val seq: Int)
    }
