package ru.skatelab.capture.presentation.calibration

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.usecase.CalibrateSensorUseCase
import javax.inject.Inject

@HiltViewModel
class CalibrationViewModel @Inject constructor(
    private val calibrateSensorUseCase: CalibrateSensorUseCase,
) : ViewModel() {

    private val _leftCalibration = MutableStateFlow<CalibrationData?>(null)
    val leftCalibration: StateFlow<CalibrationData?> = _leftCalibration

    private val _rightCalibration = MutableStateFlow<CalibrationData?>(null)
    val rightCalibration: StateFlow<CalibrationData?> = _rightCalibration

    private val _isCalibrating = MutableStateFlow(false)
    val isCalibrating: StateFlow<Boolean> = _isCalibrating

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    fun calibrate(sensorId: SensorId) {
        viewModelScope.launch {
            _isCalibrating.value = true
            _error.value = null
            calibrateSensorUseCase.invoke(sensorId)
                .onSuccess { data ->
                    when (sensorId) {
                        SensorId.LEFT -> _leftCalibration.value = data
                        SensorId.RIGHT -> _rightCalibration.value = data
                    }
                }
                .onFailure { _error.value = it.message }
            _isCalibrating.value = false
        }
    }
}
