package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class AccCalibrateSensorUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: AccCalibrateSensorUseCase

    @Before
    fun setUp() {
        bleRepository = mockk()
        useCase = AccCalibrateSensorUseCase(bleRepository)
    }

    @Test
    fun invoke_delegatesToBleRepository() =
        runTest {
            coEvery { bleRepository.accCalibrateSensor(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)
            assertTrue(result.isSuccess)
        }

    @Test
    fun invoke_propagatesFailure() =
        runTest {
            val error = IllegalStateException("Sensor not connected")
            coEvery { bleRepository.accCalibrateSensor(SensorId.RIGHT) } returns Result.failure(error)

            val result = useCase(SensorId.RIGHT)
            assertTrue(result.isFailure)
            assertEquals("Sensor not connected", result.exceptionOrNull()!!.message)
        }

    @Test
    fun invoke_rightSensor_callsRightSensor() =
        runTest {
            coEvery { bleRepository.accCalibrateSensor(SensorId.RIGHT) } returns Result.success(Unit)

            val result = useCase(SensorId.RIGHT)
            assertTrue(result.isSuccess)
        }
}
