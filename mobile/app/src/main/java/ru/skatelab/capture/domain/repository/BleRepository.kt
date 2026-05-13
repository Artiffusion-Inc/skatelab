package ru.skatelab.capture.domain.repository

import kotlinx.coroutines.flow.Flow
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId

data class ScanDevice(val name: String, val address: String, val rssi: Int)

interface BleRepository {
    val scanResults: Flow<List<ScanDevice>>
    val connectionState: Flow<Map<SensorId, ConnectionState>>
    val imuSamples: Flow<Pair<SensorId, ImuSample>>
    val reconnectEvents: Flow<SensorId>

    fun startScan()
    fun stopScan()
    suspend fun connect(sensorId: SensorId, address: String): Result<Unit>
    suspend fun disconnect(sensorId: SensorId): Result<Unit>
    suspend fun configureSensor(sensorId: SensorId): Result<Unit>
    suspend fun configureSensorNoAccCal(sensorId: SensorId): Result<Unit>
    suspend fun factoryResetSensor(sensorId: SensorId): Result<Unit>
    suspend fun startStreaming(sensorId: SensorId): Result<Unit>
    suspend fun stopStreaming(sensorId: SensorId): Result<Unit>
    suspend fun readBattery(sensorId: SensorId): Result<Int>
    suspend fun readChipTime(sensorId: SensorId): Result<Long>

    enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }
}
