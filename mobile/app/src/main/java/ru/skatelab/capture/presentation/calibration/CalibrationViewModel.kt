package ru.skatelab.capture.presentation.calibration

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.usecase.CalibrateSensorUseCase
import ru.skatelab.capture.presentation.SessionState
import javax.inject.Inject

data class QuaternionPreview(
    val w: Float = 0f,
    val x: Float = 0f,
    val y: Float = 0f,
    val z: Float = 0f,
)

@HiltViewModel
class CalibrationViewModel @Inject constructor(
    private val calibrateSensorUseCase: CalibrateSensorUseCase,
    private val bleRepository: BleRepository,
) : ViewModel() {

    private val _leftCalibration = MutableStateFlow<CalibrationData?>(null)
    val leftCalibration: StateFlow<CalibrationData?> = _leftCalibration

    private val _rightCalibration = MutableStateFlow<CalibrationData?>(null)
    val rightCalibration: StateFlow<CalibrationData?> = _rightCalibration

    private val _isCalibrating = MutableStateFlow(false)
    val isCalibrating: StateFlow<Boolean> = _isCalibrating

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error

    private val _leftQuat = MutableStateFlow(QuaternionPreview())
    val leftQuat: StateFlow<QuaternionPreview> = _leftQuat.asStateFlow()

    private val _rightQuat = MutableStateFlow(QuaternionPreview())
    val rightQuat: StateFlow<QuaternionPreview> = _rightQuat.asStateFlow()

    private var previewJob: Job? = null
    private var streamingSensors = mutableSetOf<SensorId>()

    fun startPreview(sensorId: SensorId) {
        if (sensorId in streamingSensors) return
        streamingSensors.add(sensorId)

        viewModelScope.launch {
            bleRepository.startStreaming(sensorId)
                .onFailure { _error.value = "Start streaming failed: ${it.message}" }
        }

        if (previewJob?.isActive != true) {
            previewJob = viewModelScope.launch {
                bleRepository.imuSamples.collect { (id, sample) ->
                    when (id) {
                        SensorId.LEFT -> _leftQuat.value = sample.toQuaternionPreview()
                        SensorId.RIGHT -> _rightQuat.value = sample.toQuaternionPreview()
                    }
                }
            }
        }
    }

    fun stopPreview() {
        previewJob?.cancel()
        previewJob = null
        val toStop = streamingSensors.toList()
        streamingSensors.clear()
        viewModelScope.launch {
            for (id in toStop) {
                bleRepository.stopStreaming(id)
            }
        }
    }

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
                    val calMap = mutableMapOf<SensorId, CalibrationData>()
                    _leftCalibration.value?.let { calMap[SensorId.LEFT] = it }
                    _rightCalibration.value?.let { calMap[SensorId.RIGHT] = it }
                    SessionState.calibration = calMap
                }
                .onFailure { _error.value = it.message }
            _isCalibrating.value = false
        }
    }

    override fun onCleared() {
        super.onCleared()
        stopPreview()
    }
}

private fun ImuSample.toQuaternionPreview() = QuaternionPreview(quatW, quatX, quatY, quatZ)
