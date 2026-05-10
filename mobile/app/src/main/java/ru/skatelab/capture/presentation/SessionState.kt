package ru.skatelab.capture.presentation

import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId

/**
 * Shared session state surviving navigation between screens.
 * Holds calibration data set during CalibrationScreen and read by RecordingScreen.
 */
object SessionState {
    var calibration: Map<SensorId, CalibrationData> = emptyMap()
}
