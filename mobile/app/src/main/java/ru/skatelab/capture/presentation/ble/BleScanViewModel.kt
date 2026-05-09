package ru.skatelab.capture.presentation.ble

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import android.util.Log
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import ru.skatelab.capture.domain.usecase.ConnectSensorUseCase
import javax.inject.Inject

@HiltViewModel
class BleScanViewModel @Inject constructor(
    private val bleRepository: BleRepository,
    private val connectSensorUseCase: ConnectSensorUseCase,
) : ViewModel() {

    private val tag = "BleScanVM"

    val scanResults: StateFlow<List<ScanDevice>> = bleRepository.scanResults
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val connectionState = bleRepository.connectionState
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyMap())

    private var _isScanning = false
    val isScanning: Boolean get() = _isScanning

    fun startScan() {
        if (_isScanning) return
        _isScanning = true
        Log.d(tag, "startScan() called")
        bleRepository.startScan()
    }

    fun stopScan() {
        _isScanning = false
        bleRepository.stopScan()
    }

    fun connectSensor(sensorId: SensorId, address: String) {
        viewModelScope.launch {
            Log.d(tag, "connectSensor: $sensorId -> $address")
            val result = connectSensorUseCase.invoke(sensorId, address)
            if (result.isFailure) {
                Log.e(tag, "connectSensor failed: ${result.exceptionOrNull()?.message}")
            } else {
                Log.i(tag, "connectSensor success: $sensorId")
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        if (_isScanning) bleRepository.stopScan()
    }
}
