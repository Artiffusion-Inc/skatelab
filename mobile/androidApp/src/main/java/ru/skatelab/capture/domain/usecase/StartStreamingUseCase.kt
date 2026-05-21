package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class StartStreamingUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
    ) {
        suspend operator fun invoke(sensorId: SensorId): Result<Unit> = bleRepository.startStreaming(sensorId)
    }
