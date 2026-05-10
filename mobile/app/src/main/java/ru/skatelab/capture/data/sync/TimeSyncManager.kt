package ru.skatelab.capture.data.sync

import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class TimeSyncManager @Inject constructor(
    private val bleRepository: BleRepository,
) {
    companion object {
        private const val INITIAL_SAMPLE_COUNT = 20
        private const val PERIODIC_INTERVAL_MS = 30_000L
        private const val EMA_ALPHA = 0.3f
    }

    private val offsets = mutableMapOf<SensorId, Long>()
    private val initialSamples = mutableMapOf<SensorId, MutableList<Long>>()

    /** Record a BLE packet arrival for initial offset calculation. */
    fun recordPacketArrival(sensorId: SensorId, androidNs: Long, chipTimeMs: Long) {
        val samples = initialSamples.getOrPut(sensorId) { mutableListOf() }
        if (samples.size < INITIAL_SAMPLE_COUNT) {
            val offsetNs = chipTimeMs * 1_000_000L - androidNs
            samples.add(offsetNs)
        }
        if (samples.size >= INITIAL_SAMPLE_COUNT && sensorId !in offsets) {
            offsets[sensorId] = median(samples)
        }
    }

    /** Update offset with periodic 0x50 register read. EMA smoothing. */
    fun updatePeriodicOffset(sensorId: SensorId, androidNs: Long, chipTimeMs: Long) {
        val newOffsetNs = chipTimeMs * 1_000_000L - androidNs
        val current = offsets[sensorId]
        if (current != null) {
            offsets[sensorId] = (EMA_ALPHA * newOffsetNs + (1 - EMA_ALPHA) * current).toLong()
        } else {
            offsets[sensorId] = newOffsetNs
        }
    }

    fun getOffset(sensorId: SensorId): Long = offsets[sensorId] ?: 0L

    fun isInitialized(sensorId: SensorId): Boolean = sensorId in offsets

    private fun median(values: List<Long>): Long {
        val sorted = values.sorted()
        val mid = sorted.size / 2
        return if (sorted.size % 2 == 0) (sorted[mid - 1] + sorted[mid]) / 2 else sorted[mid]
    }
}
