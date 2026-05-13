package ru.skatelab.capture.domain.usecase

import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject

class ConnectSensorUseCase @Inject constructor(
    private val bleRepository: BleRepository,
) {
    /** Connect and configure sensor using BLE-protocol sequence (factory reset + output rate). */
    suspend fun invoke(sensorId: SensorId, address: String): Result<Unit> {
        bleRepository.connect(sensorId, address).getOrElse { return Result.failure(it) }
        return bleRepository.bleConfigure(sensorId)
    }
}
