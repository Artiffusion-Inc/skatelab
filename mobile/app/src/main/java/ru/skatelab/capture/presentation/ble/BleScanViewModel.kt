package ru.skatelab.capture.presentation.ble

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.AccCalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import ru.skatelab.capture.domain.usecase.FactoryResetSensorUseCase
import ru.skatelab.capture.domain.usecase.ReadSensorInfoUseCase

@HiltViewModel
class BleScanViewModel
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val connectSensorUseCase: ConnectSensorUseCase,
        private val factoryResetSensorUseCase: FactoryResetSensorUseCase,
        private val accCalibrateSensorUseCase: AccCalibrateSensorUseCase,
        private val appLogger: Logger,
        private val readSensorInfoUseCase: ReadSensorInfoUseCase,
    ) : ViewModel() {
        private val tag = "BleScanVM"

        val scanResults: StateFlow<List<ScanDevice>> =
            bleRepository.scanResults
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

        val connectionState =
            bleRepository.connectionState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyMap())

        private val _factoryResetStatus = MutableStateFlow<String?>(null)
        val factoryResetStatus: StateFlow<String?> = _factoryResetStatus.asStateFlow()

        private val _sensorInfo = MutableStateFlow<Map<SensorId, SensorInfo?>>(emptyMap())
        val sensorInfo: StateFlow<Map<SensorId, SensorInfo?>> = _sensorInfo.asStateFlow()

        init {
            viewModelScope.launch {
                connectionState.collect { stateMap ->
                    for ((sensorId, state) in stateMap) {
                        if (state == BleRepository.ConnectionState.CONNECTED && _sensorInfo.value[sensorId] == null) {
                            refreshSensorInfo(sensorId)
                        }
                    }
                }
            }
        }

        private var _isScanning = false
        val isScanning: Boolean get() = _isScanning

        fun startScan() {
            if (_isScanning) return
            _isScanning = true
            appLogger.i(tag, "startScan() called")
            bleRepository.startScan()
        }

        fun stopScan() {
            _isScanning = false
            bleRepository.stopScan()
        }

        fun connectSensor(
            sensorId: SensorId,
            address: String,
        ) {
            viewModelScope.launch {
                appLogger.i(tag, "connectSensor: $sensorId -> $address")
                val result = connectSensorUseCase(sensorId, address)
                if (result.isFailure) {
                    appLogger.e(tag, "connectSensor failed: ${result.exceptionOrNull()?.message}")
                } else {
                    appLogger.i(tag, "connectSensor success: $sensorId")
                }
            }
        }

        fun factoryResetSensor(sensorId: SensorId) {
            viewModelScope.launch {
                _factoryResetStatus.value = "Сброс ${sensorId.name.lowercase()}..."
                appLogger.i(tag, "factoryResetSensor: $sensorId")
                val result = factoryResetSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _factoryResetStatus.value = "Сброс ${sensorId.name.lowercase()} OK"
                    appLogger.i(tag, "factoryReset success: $sensorId")
                } else {
                    _factoryResetStatus.value = "Ошибка сброса: ${result.exceptionOrNull()?.message}"
                    appLogger.e(tag, "factoryReset failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun accCalibrateSensor(sensorId: SensorId) {
            viewModelScope.launch {
                _factoryResetStatus.value = "Калибровка ACC ${sensorId.name.lowercase()}... Датчик горизонтально!"
                appLogger.i(tag, "accCalibrateSensor: $sensorId")
                val result = accCalibrateSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _factoryResetStatus.value = "ACC калибровка ${sensorId.name.lowercase()} OK"
                    appLogger.i(tag, "accCalibrate success: $sensorId")
                } else {
                    _factoryResetStatus.value = "Ошибка калибровки: ${result.exceptionOrNull()?.message}"
                    appLogger.e(tag, "accCalibrate failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun refreshSensorInfo(sensorId: SensorId) {
            viewModelScope.launch {
                val result = readSensorInfoUseCase(sensorId)
                if (result.isSuccess) {
                    _sensorInfo.value = _sensorInfo.value + (sensorId to result.getOrThrow())
                }
            }
        }

        override fun onCleared() {
            super.onCleared()
            if (_isScanning) bleRepository.stopScan()
        }
    }
