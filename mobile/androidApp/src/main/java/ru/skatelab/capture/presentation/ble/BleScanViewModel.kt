package ru.skatelab.capture.presentation.ble

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.BleScanStatus
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.service.Logger
import ru.skatelab.capture.domain.usecase.AccCalibrateSensorUseCase
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import ru.skatelab.capture.domain.usecase.FactoryResetSensorUseCase

@HiltViewModel
class BleScanViewModel
    @Inject
    constructor(
        private val bleRepository: BleRepository,
        private val connectSensorUseCase: ConnectSensorUseCase,
        private val factoryResetSensorUseCase: FactoryResetSensorUseCase,
        private val accCalibrateSensorUseCase: AccCalibrateSensorUseCase,
        private val appLogger: Logger,
    ) : ViewModel() {
        private val tag = "BleScanVM"

        val scanResults: StateFlow<List<ScanDevice>> =
            bleRepository.scanResults
                .combine(bleRepository.connectionState) { scanned, stateMap ->
                    val connected = bleRepository.getConnectedDevices()
                    val scanByAddr = scanned.associateBy { it.address }
                    val mergedByAddr = scanByAddr + connected.associateBy { it.address }
                    mergedByAddr.values.toList()
                }
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

        val connectionState =
            bleRepository.connectionState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyMap())

        private val _scanStatus = MutableStateFlow<BleScanStatus?>(null)
        val scanStatus: StateFlow<BleScanStatus?> = _scanStatus.asStateFlow()

        private val _isScanning = MutableStateFlow(false)
        val isScanning: StateFlow<Boolean> = _isScanning.asStateFlow()

        fun startScan() {
            if (_isScanning.value) return
            _isScanning.value = true
            appLogger.i(tag, "startScan() called")
            bleRepository.startScan()
        }

        fun stopScan() {
            _isScanning.value = false
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
                _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.RESETTING_LEFT else BleScanStatus.RESETTING_RIGHT
                appLogger.i(tag, "factoryResetSensor: $sensorId")
                val result = factoryResetSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.RESET_OK_LEFT else BleScanStatus.RESET_OK_RIGHT
                    appLogger.i(tag, "factoryReset success: $sensorId")
                } else {
                    _scanStatus.value = BleScanStatus.RESET_FAILED
                    appLogger.e(tag, "factoryReset failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun accCalibrateSensor(sensorId: SensorId) {
            viewModelScope.launch {
                _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.CALIBRATING_LEFT else BleScanStatus.CALIBRATING_RIGHT
                appLogger.i(tag, "accCalibrateSensor: $sensorId")
                val result = accCalibrateSensorUseCase(sensorId)
                if (result.isSuccess) {
                    _scanStatus.value = if (sensorId == SensorId.LEFT) BleScanStatus.CALIBRATION_OK_LEFT else BleScanStatus.CALIBRATION_OK_RIGHT
                    appLogger.i(tag, "accCalibrate success: $sensorId")
                } else {
                    _scanStatus.value = BleScanStatus.CALIBRATION_FAILED
                    appLogger.e(tag, "accCalibrate failed: ${result.exceptionOrNull()?.message}")
                }
            }
        }

        fun getAddressForSensor(sensorId: SensorId): String? = bleRepository.getAddressForSensor(sensorId)

        override fun onCleared() {
            super.onCleared()
            if (_isScanning.value) bleRepository.stopScan()
        }
    }
