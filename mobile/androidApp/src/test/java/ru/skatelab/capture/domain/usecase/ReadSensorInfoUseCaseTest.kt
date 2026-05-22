package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ReadSensorInfoUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: ReadSensorInfoUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = ReadSensorInfoUseCase(bleRepository)
    }

    @Test
    fun `success returns SensorInfo with all fields`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.LEFT) } returns Result.success("A3F20012ABCD")
            coEvery { bleRepository.readFirmwareVersion(SensorId.LEFT) } returns Result.success("1.2.3")
            coEvery { bleRepository.readBattery(SensorId.LEFT) } returns Result.success(85)
            coEvery { bleRepository.readBatteryMv(SensorId.LEFT) } returns Result.success(3850)

            val result = useCase(SensorId.LEFT)

            assertEquals("A3F20012ABCD", result.getOrThrow().deviceId)
            assertEquals("1.2.3", result.getOrThrow().firmwareVersion)
            assertEquals(85, result.getOrThrow().batteryPercent)
            assertEquals(3850, result.getOrThrow().batteryMv)
        }

    @Test
    fun `partial failure returns SensorInfo with defaults for failed reads`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.LEFT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readFirmwareVersion(SensorId.LEFT) } returns Result.success("1.0.0")
            coEvery { bleRepository.readBattery(SensorId.LEFT) } returns Result.success(50)
            coEvery { bleRepository.readBatteryMv(SensorId.LEFT) } returns Result.failure(Exception("err"))

            val result = useCase(SensorId.LEFT)

            assertEquals("", result.getOrThrow().deviceId)
            assertEquals("1.0.0", result.getOrThrow().firmwareVersion)
            assertEquals(50, result.getOrThrow().batteryPercent)
            assertEquals(0, result.getOrThrow().batteryMv)
        }

    @Test
    fun `all failures returns SensorInfo with all defaults`() =
        runTest {
            coEvery { bleRepository.readDeviceId(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readFirmwareVersion(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readBattery(SensorId.RIGHT) } returns Result.failure(Exception("err"))
            coEvery { bleRepository.readBatteryMv(SensorId.RIGHT) } returns Result.failure(Exception("err"))

            val result = useCase(SensorId.RIGHT)

            val info = result.getOrThrow()
            assertEquals("", info.deviceId)
            assertEquals("", info.firmwareVersion)
            assertEquals(0, info.batteryPercent)
            assertEquals(0, info.batteryMv)
        }
}
