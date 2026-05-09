package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ConnectSensorUseCaseTest {

    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: ConnectSensorUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = ConnectSensorUseCase(bleRepository)
    }

    @Test
    fun connectSuccess_configuresSensor() = runTest {
        coEvery { bleRepository.connect(SensorId.LEFT, "AA:BB") } returns Result.success(Unit)
        coEvery { bleRepository.configureSensor(SensorId.LEFT) } returns Result.success(Unit)

        val result = useCase.invoke(SensorId.LEFT, "AA:BB")

        assertTrue(result.isSuccess)
        coVerify { bleRepository.configureSensor(SensorId.LEFT) }
    }

    @Test
    fun connectFailure_skipsConfigure() = runTest {
        coEvery { bleRepository.connect(SensorId.RIGHT, "CC:DD") } returns
            Result.failure(IllegalStateException("Connection failed"))

        val result = useCase.invoke(SensorId.RIGHT, "CC:DD")

        assertTrue(result.isFailure)
        coVerify(exactly = 0) { bleRepository.configureSensor(any()) }
    }

    @Test
    fun connectSuccess_configureFailure_returnsFailure() = runTest {
        coEvery { bleRepository.connect(SensorId.LEFT, "AA:BB") } returns Result.success(Unit)
        coEvery { bleRepository.configureSensor(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("Config failed"))

        val result = useCase.invoke(SensorId.LEFT, "AA:BB")

        assertTrue(result.isFailure)
    }
}
