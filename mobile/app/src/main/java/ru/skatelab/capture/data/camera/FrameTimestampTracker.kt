package ru.skatelab.capture.data.camera

import java.io.File
import java.io.FileWriter
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.math.roundToInt

/**
 * Tracks frame timestamps and writes them to a CSV file on a background thread.
 *
 * CSV format: `frame_index,timestamp_ns` header + one line per frame.
 */
class FrameTimestampTracker {

    private var writer: FileWriter? = null
    private val executor = Executors.newSingleThreadExecutor()
    private var frameCount = 0
    private var firstFrameNs: Long = 0L
    private var lastFrameNs: Long = 0L

    /**
     * Opens [file] for writing and writes the CSV header.
     * Must be called before [onFrame].
     */
    fun open(file: File) {
        writer = FileWriter(file).apply {
            write("frame_index,timestamp_ns\n")
            flush()
        }
    }

    /**
     * Records a frame with the given [timestampNs] (nanoseconds).
     * The CSV line is written asynchronously on a background thread.
     */
    fun onFrame(timestampNs: Long) {
        val index = frameCount
        if (frameCount == 0) {
            firstFrameNs = timestampNs
        }
        lastFrameNs = timestampNs
        frameCount++

        val w = writer ?: return
        executor.submit {
            w.write("$index,$timestampNs\n")
            w.flush()
        }
    }

    /**
     * Flushes pending writes and closes the file.
     * Blocks until all queued writes complete.
     */
    fun close() {
        executor.shutdown()
        executor.awaitTermination(5, TimeUnit.SECONDS)
        writer?.close()
        writer = null
    }

    /** Returns the number of frames recorded so far. */
    fun getFrameCount(): Int = frameCount

    /**
     * Computes FPS from first/last frame timestamps and frame count.
     * Returns 0 if fewer than 2 frames have been recorded.
     */
    fun computeFps(): Int {
        if (frameCount < 2) return 0
        val elapsedSec = (lastFrameNs - firstFrameNs) / 1_000_000_000.0
        if (elapsedSec <= 0.0) return 0
        val intervals = frameCount - 1
        return (intervals / elapsedSec).roundToInt()
    }

    /** Returns the timestamp (ns) of the first recorded frame. */
    fun getFirstFrameNs(): Long = firstFrameNs

    /** Returns the timestamp (ns) of the last recorded frame. */
    fun getLastFrameNs(): Long = lastFrameNs
}
