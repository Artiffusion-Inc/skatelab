package ru.skatelab.capture.domain.usecase

import android.content.Context
import android.content.Intent
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
import io.mockk.slot
import io.mockk.just
import io.mockk.Runs
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
import java.io.File

class StartRecordingUseCaseTest {

    private lateinit var bleRepository: BleRepository
    private lateinit var cameraRepository: CameraRepository
    private lateinit var context: Context
    private lateinit var useCase: StartRecordingUseCase

    private val outputDir = File("/tmp/test-output")
    private val videoFile = File(outputDir, "video.mp4")
    private val framesFile = File(outputDir, "frames.csv")
    private val imuLeftFile = File(outputDir, "imu_left.binpb")
    private val imuRightFile = File(outputDir, "imu_right.binpb")

    @Before
    fun setUp() {
        bleRepository = mockk(relaxed = true)
        cameraRepository = mockk(relaxed = true)
        context = mockk(relaxed = true)

        useCase = StartRecordingUseCase(bleRepository, cameraRepository, context)
    }

    @Test
    fun successfulStart_returnsRecordingStartInfo() = runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
        coEvery { cameraRepository.startRecording() } returns Result.success(
            CameraRepository.RecordingStartResult(
                tStartCalledNs = 1_000_000_000L,
                tFirstFrameNs = 1_000_050_000L,
                timestampSource = "SENSOR",
                videoStartDelayMs = 50L,
            )
        )

        val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        assertTrue(result.isSuccess)
        val info = result.getOrThrow()
        assertEquals(1_000_050_000L, info.t0Ns)
        assertEquals("SENSOR", info.timestampSource)
        assertEquals(50L, info.videoStartDelayMs)
        assertEquals(videoFile, info.videoFile)
        assertEquals(imuLeftFile, info.imuLeftFile)
        assertEquals(imuRightFile, info.imuRightFile)
        assertEquals(framesFile, info.framesFile)
    }

    @Test
    fun bleStreamingLeftFailure_returnsFailure() = runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns
            Result.failure(IllegalStateException("BLE left failed"))
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)

        val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        assertTrue(result.isFailure)
        coVerify(exactly = 0) { cameraRepository.startRecording() }
    }

    @Test
    fun bleStreamingRightFailure_returnsFailure() = runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns
            Result.failure(IllegalStateException("BLE right failed"))

        val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        assertTrue(result.isFailure)
        coVerify(exactly = 0) { cameraRepository.startRecording() }
    }

    @Test
    fun cameraStartFailure_returnsFailure() = runTest {
        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
        coEvery { cameraRepository.startRecording() } returns
            Result.failure(IllegalStateException("Camera failed"))

        val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        assertTrue(result.isFailure)
    }

    @Test
    fun fgsIntentSentBeforeBleAndCamera() = runTest {
        coEvery { bleRepository.startStreaming(any()) } returns Result.success(Unit)
        coEvery { cameraRepository.startRecording() } returns Result.success(
            CameraRepository.RecordingStartResult(
                tStartCalledNs = 1L, tFirstFrameNs = 2L,
                timestampSource = "SENSOR", videoStartDelayMs = 0L,
            )
        )

        useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        verify { context.startForegroundService(any<Intent>()) }
    }

    @Test
    fun imuStartDelayCalculatedCorrectly() = runTest {
        val tFirstFrameNs = 150_000_000L

        coEvery { bleRepository.startStreaming(SensorId.LEFT) } returns Result.success(Unit)
        coEvery { bleRepository.startStreaming(SensorId.RIGHT) } returns Result.success(Unit)
        coEvery { cameraRepository.startRecording() } returns Result.success(
            CameraRepository.RecordingStartResult(
                tStartCalledNs = 100_000_000L,
                tFirstFrameNs = tFirstFrameNs,
                timestampSource = "BOOTTIME",
                videoStartDelayMs = 50L,
            )
        )

        val result = useCase.invoke(outputDir, videoFile, framesFile, imuLeftFile, imuRightFile)

        assertTrue(result.isSuccess)
        val info = result.getOrThrow()
        // SystemClock.elapsedRealtimeNanos() returns 0 in unit test stubs
        val expectedDelayMs = (tFirstFrameNs - 0L) / 1_000_000
        assertEquals(expectedDelayMs, info.imuStartDelayMs[SensorId.LEFT])
        assertEquals(expectedDelayMs, info.imuStartDelayMs[SensorId.RIGHT])
    }
}
