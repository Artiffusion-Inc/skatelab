package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.verify
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.CameraRepository
import ru.skatelab.capture.service.SensorRecordingService

class StopRecordingUseCaseTest {

    private lateinit var bleRepository: BleRepository
    private lateinit var cameraRepository: CameraRepository
    private lateinit var context: Context
    private lateinit var useCase: StopRecordingUseCase

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        cameraRepository = mockk(relaxed = true)
        context = mockk(relaxed = true)

        useCase = StopRecordingUseCase(bleRepository, cameraRepository, context)
    }

    @Test
    fun successfulStop_stopsCameraAndBleAndFgs() = runTest {
        coEvery { cameraRepository.stopRecording() } returns Result.success(
            CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true)
        )
        coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.stopStreaming(SensorId.RIGHT) } returns Result.success(Unit)

        val result = useCase.invoke()

        assertTrue(result.isSuccess)
        coVerify { cameraRepository.stopRecording() }
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
        coVerify { cameraRepository.release() }
        verify { context.startService(any()) }
    }

    @Test
    fun cameraStopFailure_propagatesErrorWithoutBleStop() = runTest {
        coEvery { cameraRepository.stopRecording() } returns
            Result.failure(IllegalStateException("Camera stop failed"))
        coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

        val result = useCase.invoke()

        // runCatching: camera stop is step 1, throws before BLE stop
        assertTrue(result.isFailure)
        coVerify(exactly = 0) { bleRepository.stopStreaming(any()) }
        coVerify(exactly = 0) { cameraRepository.release() }
    }

    @Test
    fun bleStopFailure_doesNotPreventOtherCleanup() = runTest {
        coEvery { cameraRepository.stopRecording() } returns Result.success(
            CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true)
        )
        // LEFT fails, RIGHT succeeds — getOrDefault(Unit) swallows failure
        coEvery { bleRepository.stopStreaming(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("BLE stop failed"))
        coEvery { bleRepository.stopStreaming(SensorId.RIGHT) } returns Result.success(Unit)

        val result = useCase.invoke()

        // Both BLE stops attempted, failure swallowed via getOrDefault
        assertTrue(result.isSuccess)
        coVerify { bleRepository.stopStreaming(SensorId.LEFT) }
        coVerify { bleRepository.stopStreaming(SensorId.RIGHT) }
        coVerify { cameraRepository.release() }
        verify { context.startService(any()) }
    }

    @Test
    fun fgsStopIntentSentAfterCleanup() = runTest {
        coEvery { cameraRepository.stopRecording() } returns Result.success(
            CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true)
        )
        coEvery { bleRepository.stopStreaming(any()) } returns Result.success(Unit)

        useCase.invoke()

        verify { context.startService(any<Intent>()) }
    }

    @Test
    fun stopOrdering_cameraBeforeBle() = runTest {
        coEvery { cameraRepository.stopRecording() } returns Result.success(
            CameraRepository.RecordingStopResult(actualFps = 60, fpsVerified = true)
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
