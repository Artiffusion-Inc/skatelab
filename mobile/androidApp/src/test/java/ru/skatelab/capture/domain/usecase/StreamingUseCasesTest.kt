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

class StartStreamingUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: StartStreamingUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = StartStreamingUseCase(bleRepository)
    }

    @Test
    fun startStreamingSuccess() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assertTrue(result.isSuccess)
            coVerify { bleRepository.startStreaming(SensorId.LEFT) }
        }

    @Test
    fun startStreamingFailure() =
        runTest {
            coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("Not connected"))

            val result = useCase(SensorId.RIGHT)

            assertTrue(result.isFailure)
        }
}

class StopStreamingUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: StopStreamingUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = StopStreamingUseCase(bleRepository)
    }

    @Test
    fun stopStreamingSuccess() =
        runTest {
            coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assertTrue(result.isSuccess)
            coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        }

    @Test
    fun stopStreamingFailure() =
        runTest {
            coEvery { bleRepository.stopStreaming(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("Not connected"))

            val result = useCase(SensorId.RIGHT)

            assertTrue(result.isFailure)
            coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
        }
}

class FactoryResetSensorUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: FactoryResetSensorUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = FactoryResetSensorUseCase(bleRepository)
    }

    @Test
    fun factoryResetSuccess() =
        runTest {
            coEvery { bleRepository.factoryResetSensor(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assertTrue(result.isSuccess)
            coVerify { bleRepository.factoryResetSensor(SensorId.LEFT) }
        }

    @Test
    fun factoryResetFailure() =
        runTest {
            coEvery { bleRepository.factoryResetSensor(SensorId.RIGHT) } returns
                Result.failure(IOException("Write failed"))

            val result = useCase(SensorId.RIGHT)

            assertTrue(result.isFailure)
        }

    private class IOException(msg: String) : java.io.IOException(msg)
}

class AccCalibrateSensorUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: AccCalibrateSensorUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = AccCalibrateSensorUseCase(bleRepository)
    }

    @Test
    fun accCalibrateSuccess() =
        runTest {
            coEvery { bleRepository.accCalibrateSensor(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assertTrue(result.isSuccess)
            coVerify { bleRepository.accCalibrateSensor(SensorId.LEFT) }
        }

    @Test
    fun accCalibrateFailure() =
        runTest {
            coEvery { bleRepository.accCalibrateSensor(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("Not connected"))

            val result = useCase(SensorId.RIGHT)

            assertTrue(result.isFailure)
        }
}
