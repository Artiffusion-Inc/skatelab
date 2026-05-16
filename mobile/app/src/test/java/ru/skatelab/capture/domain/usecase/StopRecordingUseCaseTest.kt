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
import ru.skatelab.capture.domain.repository.CameraRepository

class StopRecordingUseCaseTest {
    private lateinit var bleRepository: BleRepository
    private lateinit var cameraRepository: CameraRepository
    private lateinit var useCase: StopRecordingUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        cameraRepository = mockk(relaxed = true)

        useCase = StopRecordingUseCase(bleRepository, cameraRepository)
    }

    @Test
    fun successfulStop_stopsCameraAndBle() =
        runTest {
            coEvery { cameraRepository.stopRecording() } returns
                Result.success(
                    CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true, firstFrameNs = 1_000_050_000_000L),
                )
            coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns Result.success(Unit)
            coEvery { bleRepository.stopStreaming(SensorId.RIGHT) } returns Result.success(Unit)

            val result = useCase.invoke()

            assertTrue(result.isSuccess)
            coVerify { cameraRepository.stopRecording() }
            coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
            coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
            coVerify { cameraRepository.release() }
        }

    @Test
    fun cameraStopFailure_propagatesErrorWithoutBleStop() =
        runTest {
            coEvery { cameraRepository.stopRecording() } returns
                Result.failure(IllegalStateException("Camera stop failed"))
            coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

            val result = useCase.invoke()

            assertTrue(result.isFailure)
            coVerify(exactly = 0) { bleRepository.stopStreaming(any()) }
            coVerify(exactly = 0) { cameraRepository.release() }
        }

    @Test
    fun bleStopFailure_doesNotPreventOtherCleanup() =
        runTest {
            coEvery { cameraRepository.stopRecording() } returns
                Result.success(
                    CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true, firstFrameNs = 1_000_050_000_000L),
                )
            coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns
                Result.failure(IllegalStateException("BLE stop failed"))
            coEvery { bleRepository.stopStreaming(SensorId.RIGHT) } returns Result.success(Unit)

            val result = useCase.invoke()

            assertTrue(result.isSuccess)
            coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
            coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
            coVerify { cameraRepository.release() }
        }

    @Test
    fun stopOrdering_cameraBeforeBle() =
        runTest {
            coEvery { cameraRepository.stopRecording() } returns
                Result.success(
                    CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true, firstFrameNs = 1_000_050_000_000L),
                )
            coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

            useCase.invoke()

            coVerify(ordering = io.mockk.Ordering.ORDERED) {
                cameraRepository.stopRecording()
                bleRepository.stopStreaming(SensorId.LEFT)
                bleRepository.stopStreaming(SensorId.RIGHT)
                cameraRepository.release()
            }
        }
}
