package ru.skatelab.capture.domain.usecase

import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.model.SensorInfo
import ru.skatelab.capture.domain.repository.BleRepository

class ReadSensorInfoUseCase
    @Inject
    constructor(
        private val bleRepository: BleRepository,
    ) {
        suspend operator fun invoke(sensorId: SensorId): Result<SensorInfo> =
            runCatching {
                coroutineScope {
                    val deviceIdDeferred = async { bleRepository.readDeviceId(sensorId).getOrDefault("") }
                    val firmwareDeferred = async { bleRepository.readFirmwareVersion(sensorId).getOrDefault("") }
                    val batteryPercentDeferred = async { bleRepository.readBattery(sensorId).getOrDefault(0) }
                    val batteryMvDeferred = async { bleRepository.readBatteryMv(sensorId).getOrDefault(0) }
                    SensorInfo(
                        deviceId = deviceIdDeferred.await(),
                        firmwareVersion = firmwareDeferred.await(),
                        batteryPercent = batteryPercentDeferred.await(),
                        batteryMv = batteryMvDeferred.await(),
                    )
                }
            }
    }
