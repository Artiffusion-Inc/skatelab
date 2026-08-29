package ru.skatelab.capture.domain.service

import java.io.File
import kotlinx.coroutines.CoroutineScope
import ru.skatelab.capture.domain.model.SensorId

interface ImuCollector {
    fun start(
        scope: CoroutineScope,
        files: Map<SensorId, File>,
    )

    fun stop(): Map<SensorId, Int>

    /** First persisted sample timestamp for the current capture, if any. */
    fun firstSampleTimestampNs(sensorId: SensorId): Long?
}
