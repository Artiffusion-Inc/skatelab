package ru.skatelab.capture.data.camera

import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class FrameTimestampTrackerTest {
    @Test
    fun `write 2 frames and read back CSV`() {
        val tempFile = File.createTempFile("frame_timestamps", ".csv")
        tempFile.deleteOnExit()

        val tracker = FrameTimestampTracker()

        // Open tracker
        tracker.open(tempFile)

        // Write 2 frames
        tracker.onFrame(1_000_000_000L)
        tracker.onFrame(1_016_666_667L) // ~16.67ms later (60fps)

        // Close and flush
        tracker.close()

        // Read back CSV
        val lines = tempFile.readLines()
        assertTrue("CSV should have at least 3 lines (header + 2 data)", lines.size >= 3)

        // Verify header
        assertEquals("frame_index,timestamp_ns", lines[0].trim())

        // Verify frame 0
        val frame0 = lines[1].trim().split(",")
        assertEquals(2, frame0.size)
        assertEquals("0", frame0[0])
        assertEquals("1000000000", frame0[1])

        // Verify frame 1
        val frame1 = lines[2].trim().split(",")
        assertEquals(2, frame1.size)
        assertEquals("1", frame1[0])
        assertEquals("1016666667", frame1[1])
    }

    @Test
    fun `computeFps returns correct rate for 60fps data`() {
        val tracker = FrameTimestampTracker()
        val tempFile = File.createTempFile("frame_timestamps", ".csv")
        tempFile.deleteOnExit()

        tracker.open(tempFile)

        // Simulate 60fps: 10 frames, 16.67ms apart
        for (i in 0 until 10) {
            tracker.onFrame(1_000_000_000L + i * 16_666_667L)
        }

        assertEquals(10, tracker.getFrameCount())
        assertEquals(60, tracker.computeFps())

        tracker.close()
    }

    @Test
    fun `firstFrameNs and lastFrameNs tracking`() {
        val tracker = FrameTimestampTracker()
        val tempFile = File.createTempFile("frame_timestamps", ".csv")
        tempFile.deleteOnExit()

        tracker.open(tempFile)
        tracker.onFrame(1_000_000_000L)
        tracker.onFrame(2_000_000_000L)

        assertEquals(1_000_000_000L, tracker.getFirstFrameNs())
        assertEquals(2_000_000_000L, tracker.getLastFrameNs())

        tracker.close()
    }

    @Test
    fun `computeFps returns 0 for single frame`() {
        val tracker = FrameTimestampTracker()
        tracker.onFrame(1_000_000_000L)

        assertEquals(0, tracker.computeFps())
    }

    @Test
    fun `computeFps returns 0 for zero-duration frames`() {
        val tracker = FrameTimestampTracker()
        tracker.onFrame(1_000_000_000L)
        tracker.onFrame(1_000_000_000L)

        assertEquals(0, tracker.computeFps())
    }

    @Test
    fun `computeFps returns 30 for 30fps data`() {
        val tracker = FrameTimestampTracker()

        for (i in 0 until 10) {
            tracker.onFrame(1_000_000_000L + i * 33_333_333L)
        }

        assertEquals(30, tracker.computeFps())
    }
}
