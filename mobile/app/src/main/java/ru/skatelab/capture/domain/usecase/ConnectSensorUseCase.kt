package ru.skatelab.capture.domain.usecase

import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import javax.inject.Inject

class ConnectSensorUseCase @Inject constructor(
    private val bleRepository: BleRepository,
) {
    /** Connect sensor. BleManager sends setRate(0x09) automatically after service discovery. */
    suspend fun invoke(sensorId: SensorId, address: String): Result<Unit> {
        return bleRepository.connect(sensorId, address)
    }
}