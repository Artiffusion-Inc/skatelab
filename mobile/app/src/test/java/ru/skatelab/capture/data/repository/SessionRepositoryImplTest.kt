package ru.skatelab.capture.data.repository

import android.content.Context
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.After
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import java.io.File

class SessionRepositoryImplTest {

    private lateinit var tempDir: File
    private lateinit var context: Context
    private lateinit var appLogger: AppLogger
    private lateinit var repository: SessionRepositoryImpl

    @Before
    fun setUp() {
        tempDir = createTempDir("session_repo_test")
        context = mockk(relaxed = true)
        every { context.filesDir } returns tempDir
        appLogger = mockk(relaxed = true)
        repository = SessionRepositoryImpl(context, appLogger)
    }

    @After
    fun tearDown() {
        tempDir.deleteRecursively()
    }

    private fun createSession(
        id: String = "test-session-1",
        isComplete: Boolean = true,
    ): CaptureSession {
        val sessionDir = File(tempDir, "sessions/$id")
        sessionDir.mkdirs()
        return CaptureSession(
            id = id,
            videoFile = File(sessionDir, "video.mp4"),
            imuLeftFile = File(sessionDir, "imu_left.binpb"),
            imuRightFile = File(sessionDir, "imu_right.binpb"),
            frameTimestampsFile = File(sessionDir, "frames.csv"),
            manifestFile = File(sessionDir, "manifest.json"),
            t0Ns = 1_000_000_000L,
            durationMs = 5000L,
            videoFps = 60,
            timestampSource = "REALTIME",
            videoStartDelayMs = 120L,
            imuStartDelayMs = mapOf(SensorId.LEFT to 480L, SensorId.RIGHT to 490L),
            calibration = mapOf(
                SensorId.LEFT to CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L),
                SensorId.RIGHT to CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L),
            ),
            clockOffsetNs = mapOf(SensorId.LEFT to 12345L, SensorId.RIGHT to 67890L),
            createdAt = 1_700_000_000_000L,
            isComplete = isComplete,
        )
    }

    @Test
    fun saveAndGetSession_roundTripsCorrectly() = runTest {
        val session = createSession()

        val saveResult = repository.saveSession(session)
        assertTrue("Save should succeed", saveResult.isSuccess)

        val loaded = repository.getSession(session.id)
        assertNotNull("Session should be found after save", loaded)
        loaded!!.let { s ->
            assertEquals(session.id, s.id)
            assertEquals(session.videoFile.absolutePath, s.videoFile.absolutePath)
            assertEquals(session.imuLeftFile.absolutePath, s.imuLeftFile.absolutePath)
            assertEquals(session.imuRightFile.absolutePath, s.imuRightFile.absolutePath)
            assertEquals(session.frameTimestampsFile.absolutePath, s.frameTimestampsFile.absolutePath)
            assertEquals(session.manifestFile.absolutePath, s.manifestFile.absolutePath)
            assertEquals(session.t0Ns, s.t0Ns)
            assertEquals(session.durationMs, s.durationMs)
            assertEquals(session.videoFps, s.videoFps)
            assertEquals(session.timestampSource, s.timestampSource)
            assertEquals(session.videoStartDelayMs, s.videoStartDelayMs)
            assertEquals(session.imuStartDelayMs, s.imuStartDelayMs)
            assertEquals(session.calibration, s.calibration)
            assertEquals(session.clockOffsetNs, s.clockOffsetNs)
            assertEquals(session.createdAt, s.createdAt)
            assertEquals(session.isComplete, s.isComplete)
        }
    }

    @Test
    fun getSessions_returnsEmptyListWhenNoSessionsDir() = runTest {
        // Delete the sessions dir to simulate fresh install
        File(tempDir, "sessions").deleteRecursively()

        val sessions = repository.getSessions()
        assertTrue("Should return empty list when sessions dir absent", sessions.isEmpty())
    }

    @Test
    fun deleteSession_removesSessionDirectory() = runTest {
        val session = createSession()
        repository.saveSession(session)

        val dirBefore = File(tempDir, "sessions/${session.id}")
        assertTrue("Session dir should exist after save", dirBefore.exists())

        val deleteResult = repository.deleteSession(session.id)
        assertTrue("Delete should succeed", deleteResult.isSuccess)
        assertFalse("Session dir should be removed after delete", dirBefore.exists())

        val loaded = repository.getSession(session.id)
        assertEquals("Deleted session should not be found", null, loaded)
    }
}