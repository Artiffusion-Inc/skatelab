package ru.skatelab.capture.domain.service

import kotlinx.coroutines.CoroutineScope
import ru.skatelab.capture.domain.model.SensorId

interface TimeSynchronizer {
    fun sync(scope: CoroutineScope)

    suspend fun awaitSync()

    fun stop()

    fun getOffset(sensorId: SensorId): Long
}
