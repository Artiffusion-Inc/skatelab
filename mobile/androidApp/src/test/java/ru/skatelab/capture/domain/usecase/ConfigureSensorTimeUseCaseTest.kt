package ru.skatelab.capture.domain.usecase

import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class ConfigureSensorTimeUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var useCase: ConfigureSensorTimeUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        useCase = ConfigureSensorTimeUseCase(bleRepository)
    }

    @Test
    fun `success calls configureSensorTime`() =
        runTest {
            coEvery { bleRepository.configureSensorTime(SensorId.LEFT) } returns Result.success(Unit)

            val result = useCase(SensorId.LEFT)

            assert(result.isSuccess)
            coVerify(exactly = 1) { bleRepository.configureSensorTime(SensorId.LEFT) }
        }

    @Test
    fun `failure propagates error`() =
        runTest {
            coEvery { bleRepository.configureSensorTime(SensorId.RIGHT) } returns
                Result.failure(IllegalStateException("GATT error"))

            val result = useCase(SensorId.RIGHT)

            assert(result.isFailure)
        }
}
