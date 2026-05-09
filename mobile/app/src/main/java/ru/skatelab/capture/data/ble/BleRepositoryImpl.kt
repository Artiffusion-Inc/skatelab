package ru.skatelab.capture.data.ble

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BleRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
) : BleRepository {

    private val bleManager = BleManager(context)
    private val _addressMap = mutableMapOf<SensorId, String>()

    override val scanResults: Flow<List<ScanDevice>> = bleManager.scanResults.map { results ->
        results.map { ScanDevice(name = it.name, address = it.address, rssi = it.rssi) }
    }

    override val connectionState: Flow<Map<SensorId, BleRepository.ConnectionState>> =
        bleManager.connectionState.map { stateMap ->
            stateMap.mapValues { (_, state) ->
                when (state) {
                    BleManager.ConnectionState.DISCONNECTED -> BleRepository.ConnectionState.DISCONNECTED
                    BleManager.ConnectionState.CONNECTING -> BleRepository.ConnectionState.CONNECTING
                    BleManager.ConnectionState.CONNECTED -> BleRepository.ConnectionState.CONNECTED
                    BleManager.ConnectionState.RECONNECTING -> BleRepository.ConnectionState.RECONNECTING
                }
            }
        }

    override val imuSamples: Flow<Pair<SensorId, ImuSample>> = bleManager.imuSamples

    override fun startScan() = bleManager.startScan()
    override fun stopScan() = bleManager.stopScan()

    override suspend fun connect(sensorId: SensorId, address: String): Result<Unit> {
        val result = bleManager.connect(sensorId, address)
        if (result.isSuccess) _addressMap[sensorId] = address
        return result
    }

    override suspend fun disconnect(sensorId: SensorId): Result<Unit> = runCatching {
        val address = _addressMap.remove(sensorId) ?: return Result.success(Unit)
        bleManager.disconnect(sensorId, address)
    }

    override suspend fun configureSensor(sensorId: SensorId): Result<Unit> = runCatching {
        bleManager.sendSequence(sensorId, Wt901Commander.configureSequence())
    }

    override suspend fun startStreaming(sensorId: SensorId): Result<Unit> = runCatching {
        bleManager.sendSequence(sensorId, Wt901Commander.startStreamingSequence())
    }

    override suspend fun stopStreaming(sensorId: SensorId): Result<Unit> = runCatching {
        bleManager.sendSequence(sensorId, Wt901Commander.stopStreamingSequence())
    }

    override suspend fun readBattery(sensorId: SensorId): Result<Int> = runCatching {
        bleManager.sendCommand(sensorId, Wt901Commander.readRegister(0x04))
        // Battery response comes via 0x71 notification - for now return placeholder
        100
    }

    override suspend fun readChipTime(sensorId: SensorId): Result<Long> = runCatching {
        bleManager.sendCommand(sensorId, Wt901Commander.readRegister(0x50))
        // Chip time response comes via 0x71 notification - for now return system time
        System.currentTimeMillis()
    }
}
