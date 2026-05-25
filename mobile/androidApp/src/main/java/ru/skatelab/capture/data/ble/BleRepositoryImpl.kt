package ru.skatelab.capture.data.ble

import android.content.Context
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice

@Singleton
class BleRepositoryImpl
    @Inject
    constructor(
        @ApplicationContext private val context: Context,
        private val appLogger: ru.skatelab.capture.AppLogger,
    ) : BleRepository {
        private val bleManager = BleManager(context, appLogger)

        @Suppress("ktlint:standard:property-naming")
        private val _addressMap = ConcurrentHashMap<SensorId, String>()

        override val scanResults: Flow<List<ScanDevice>> =
            bleManager.scanResults.map { results ->
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

        override val reconnectEvents: Flow<SensorId> = bleManager.reconnectEvents

        override fun startScan() = bleManager.startScan()

        override fun stopScan() = bleManager.stopScan()

        override suspend fun connect(
            sensorId: SensorId,
            address: String,
        ): Result<Unit> {
            val result = bleManager.connect(sensorId, address)
            if (result.isSuccess) _addressMap[sensorId] = address
            return result
        }

        override suspend fun disconnect(sensorId: SensorId): Result<Unit> =
            runCatching {
                val address = _addressMap.remove(sensorId) ?: return Result.success(Unit)
                bleManager.disconnect(sensorId, address)
            }

        override suspend fun factoryResetSensor(sensorId: SensorId): Result<Unit> =
            runCatching {
                bleManager.sendCommand(sensorId, Wt901Commander.factoryReset())
            }

        override suspend fun accCalibrateSensor(sensorId: SensorId): Result<Unit> =
            runCatching {
                bleManager.sendSequence(sensorId, Wt901Commander.bleAccCalibrateSequence())
            }

        /** No-op in BLE mode — 0x61 streams automatically when CCCD is enabled. */
        override suspend fun startStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        /** No-op in BLE mode — streaming stops when sensor disconnects. */
        override suspend fun stopStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        override suspend fun readBattery(sensorId: SensorId): Result<Int> {
            val result = bleManager.readRegisterResponse(sensorId, 0x64)
            return result.map { data ->
                BleRepository.rawBatteryToPercent(data[0].toInt())
            }
        }

        override suspend fun readChipTime(sensorId: SensorId): Result<Long> {
            val result = bleManager.readRegisterResponse(sensorId, 0x50)
            return result.map { data ->
                val low = data[0].toLong() and 0xFFFF
                val mid = data[1].toLong() and 0xFFFF
                val high = data[2].toLong() and 0xFFFF
                (high shl 32) or (mid shl 16) or low
            }
        }

        override suspend fun readDeviceId(sensorId: SensorId): Result<String> =
            runCatching {
                val data = bleManager.readRegisterResponse(sensorId, 0x68).getOrThrow()
                "%04X%04X%04X".format(data[0].toInt() and 0xFFFF, data[1].toInt() and 0xFFFF, data[2].toInt() and 0xFFFF)
            }

        override suspend fun readFirmwareVersion(sensorId: SensorId): Result<String> =
            runCatching {
                val data = bleManager.readRegisterResponse(sensorId, 0x60).getOrThrow()
                val major = (data[0].toInt() and 0xFFFF) shr 8
                val minor = data[0].toInt() and 0xFF
                val patch = (data[1].toInt() and 0xFF00) shr 8
                "$major.$minor.$patch"
            }

        override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
            runCatching {
                val data = bleManager.readRegisterResponse(sensorId, 0x64).getOrThrow()
                data[0].toInt() // Raw value — unit unverified. TODO: compare with multimeter.
            }

        override suspend fun configureSensorTime(sensorId: SensorId): Result<Unit> =
            runCatching {
                bleManager.sendSequence(sensorId, Wt901Commander.timeConfigSequence())
            }

        override fun getConnectedDevices(): List<ScanDevice> =
            bleManager.getConnectedDevices().map { ScanDevice(name = it.name, address = it.address, rssi = it.rssi, isConnected = true) }

        override fun getAddressForSensor(sensorId: SensorId): String? = _addressMap[sensorId]
    }
