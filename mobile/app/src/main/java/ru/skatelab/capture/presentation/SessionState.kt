package ru.skatelab.capture.presentation

import javax.inject.Inject
import javax.inject.Singleton
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId

@Singleton
class SessionState
    @Inject
    constructor() {
        var calibration: Map<SensorId, CalibrationData> = emptyMap()
    }
