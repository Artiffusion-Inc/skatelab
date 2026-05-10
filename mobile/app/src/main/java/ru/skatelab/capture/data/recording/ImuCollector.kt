package ru.skatelab.capture.data.recording

import ru.skatelab.capture.AppLogger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.export.ImuStreamWriter
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Collects IMU samples from BLE sensors and writes them to .binpb files during recording.
 *
 * Opens [ImuStreamWriter] per sensor on [start], collects from [BleRepository.imuSamples]
 * flow, and writes each sample. Closes writers on [stop] and returns sample counts.
 */
@Singleton
class ImuCollector @Inject constructor(
    private val bleRepository: BleRepository,
    private val appLogger: AppLogger,
) {
    companion object {
        private const val TAG = "ImuCollector"
    }

    private val writers = mutableMapOf<SensorId, ImuStreamWriter>()
    private val counts = mutableMapOf<SensorId, Int>()
    private var collectJob: kotlinx.coroutines.Job? = null

    /**
     * Start collecting IMU samples for the given sensors.
     * @param scope Coroutine scope for the collection job.
     * @param files Map of sensor ID to output .binpb file.
     */
    fun start(scope: CoroutineScope, files: Map<SensorId, File>) {
        files.forEach { (sensorId, file) ->
            val writer = ImuStreamWriter()
            writer.open(file)
            writers[sensorId] = writer
            counts[sensorId] = 0
            appLogger.i(TAG, "Started IMU writer for $sensorId → ${file.absolutePath}")
        }

        collectJob = scope.launch(Dispatchers.IO) {
            bleRepository.imuSamples
                .filter { (id, _) -> writers.containsKey(id) }
                .collect { (sensorId, sample) ->
                    val writer = writers[sensorId] ?: return@collect
                    try {
                        writer.write(sample)
                        counts[sensorId] = counts.getOrDefault(sensorId, 0) + 1
                    } catch (e: Exception) {
                        appLogger.e(TAG, "Write error for $sensorId: ${e.message}")
                    }
                }
        }
    }

    /**
     * Stop collecting and close all writers.
     * @return Map of sensor ID to sample count written.
     */
    fun stop(): Map<SensorId, Int> {
        collectJob?.cancel()
        collectJob = null
        writers.forEach { (sensorId, writer) ->
            try {
                writer.close()
                appLogger.i(TAG, "Closed IMU writer for $sensorId, ${counts[sensorId]} samples")
            } catch (e: Exception) {
                appLogger.e(TAG, "Close error for $sensorId: ${e.message}")
            }
        }
        writers.clear()
        return counts.toMap()
    }
}
