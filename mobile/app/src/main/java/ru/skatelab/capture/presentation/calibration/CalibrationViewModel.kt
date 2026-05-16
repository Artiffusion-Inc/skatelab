package ru.skatelab.capture.presentation.calibration

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.sample
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.usecase.CalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.StartStreamingUseCase
import ru.skatelab.capture.domain.usecase.StopStreamingUseCase
import ru.skatelab.capture.presentation.SessionState

data class QuaternionPreview(
    val w: Float = 0f,
    val x: Float = 0f,
    val y: Float = 0f,
    val z: Float = 0f,
)

@HiltViewModel
class CalibrationViewModel
    @Inject
    constructor(
        private val calibrateSensorUseCase: CalibrateSensorUseCase,
        private val startStreamingUseCase: StartStreamingUseCase,
        private val stopStreamingUseCase: StopStreamingUseCase,
        private val bleRepository: BleRepository,
        private val sessionState: SessionState,
    ) : ViewModel() {
        private val _leftCalibration = MutableStateFlow<CalibrationData?>(null)
        val leftCalibration: StateFlow<CalibrationData?> = _leftCalibration

        private val _rightCalibration = MutableStateFlow<CalibrationData?>(null)
        val rightCalibration: StateFlow<CalibrationData?> = _rightCalibration

        private val _isCalibrating = MutableStateFlow(false)
        val isCalibrating: StateFlow<Boolean> = _isCalibrating

        private val _calibrationProgress = MutableStateFlow(0)
        val calibrationProgress: StateFlow<Int> = _calibrationProgress

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
                startStreamingUseCase(sensorId)
                    .onFailure { _error.value = "Start streaming failed: ${it.message}" }
            }

            if (previewJob?.isActive != true) {
                previewJob =
                    viewModelScope.launch {
                        bleRepository.imuSamples.sample(100L).collect { (id, sample) ->
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
                    stopStreamingUseCase(id)
                }
            }
        }

        fun calibrateBoth() {
            viewModelScope.launch {
                _isCalibrating.value = true
                _error.value = null
                _calibrationProgress.value = 0
                previewJob?.cancel()
                previewJob = null
                try {
                    calibrateSensorUseCase { progress ->
                        _calibrationProgress.value = progress
                    }
                        .onSuccess { calMap ->
                            calMap[SensorId.LEFT]?.let { _leftCalibration.value = it }
                            calMap[SensorId.RIGHT]?.let { _rightCalibration.value = it }
                            sessionState.calibration = calMap
                        }
                        .onFailure { _error.value = it.message }
                } finally {
                    _calibrationProgress.value = 100
                    delay(500L)
                    _isCalibrating.value = false
                    restartPreviewCollection()
                }
            }
        }

        private fun restartPreviewCollection() {
            if (previewJob?.isActive == true) return
            if (streamingSensors.isEmpty()) return
            previewJob =
                viewModelScope.launch {
                    bleRepository.imuSamples.sample(100L).collect { (id, sample) ->
                        when (id) {
                            SensorId.LEFT -> _leftQuat.value = sample.toQuaternionPreview()
                            SensorId.RIGHT -> _rightQuat.value = sample.toQuaternionPreview()
                        }
                    }
                }
        }

        override fun onCleared() {
            super.onCleared()
            stopPreview()
        }
    }

private fun ImuSample.toQuaternionPreview() = QuaternionPreview(quatW, quatX, quatY, quatZ)
