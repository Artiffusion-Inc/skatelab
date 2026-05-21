package ru.skatelab.capture.data.ble

import javax.inject.Inject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.emptyFlow
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice

/**
 * No-op BLE repository used when BLE is unavailable or the user opts out of IMU recording.
 *
 * Returns empty flows and no-op results for all operations.
 * Camera recording works without BLE; IMU data is simply omitted.
 */
class NoOpBleRepository
    @Inject
    constructor() : BleRepository {
        override val scanResults: Flow<List<ScanDevice>> = MutableStateFlow(emptyList())
        override val connectionState: Flow<Map<SensorId, BleRepository.ConnectionState>> =
            MutableStateFlow(emptyMap())
        override val imuSamples: Flow<Pair<SensorId, ImuSample>> = emptyFlow()
        override val reconnectEvents: Flow<SensorId> = emptyFlow()

        override fun startScan() {
            // No-op
        }

        override fun stopScan() {
            // No-op
        }

        override suspend fun connect(
            sensorId: SensorId,
            address: String,
        ): Result<Unit> = Result.failure(IllegalStateException("BLE not available"))

        override suspend fun disconnect(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        override suspend fun factoryResetSensor(sensorId: SensorId): Result<Unit> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun accCalibrateSensor(sensorId: SensorId): Result<Unit> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun startStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        override suspend fun stopStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        override suspend fun readBattery(sensorId: SensorId): Result<Int> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun readChipTime(sensorId: SensorId): Result<Long> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun readDeviceId(sensorId: SensorId): Result<String> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun readFirmwareVersion(sensorId: SensorId): Result<String> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
            Result.failure(IllegalStateException("BLE not available"))

        override suspend fun configureSensorTime(sensorId: SensorId): Result<Unit> =
            Result.failure(IllegalStateException("BLE not available"))

        override fun getConnectedDevices(): List<ScanDevice> = emptyList()

        override fun getAddressForSensor(sensorId: SensorId): String? = null
    }