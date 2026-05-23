package ru.skatelab.capture.data.camera

import java.io.File
import java.io.FileWriter
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import kotlin.math.roundToInt

/**
 * Tracks frame timestamps and writes them to a CSV file on a background thread.
 *
 * Uses a [LinkedBlockingQueue] for buffering to avoid executor overhead.
 * CSV format: `frame_index,timestamp_ns` header + one line per frame.
 */
class FrameTimestampTracker {
    private var writer: FileWriter? = null
    private val queue = LinkedBlockingQueue<Pair<Int, Long>>(1000)
    private var writerThread: Thread? = null

    @Volatile private var isRunning = false

    @Volatile private var frameCount = 0

    @Volatile private var firstFrameNs: Long = 0L

    @Volatile private var lastFrameNs: Long = 0L

    @Volatile private var framesSinceFlush = 0

    /**
     * Opens [file] for writing and writes the CSV header.
     * Starts the background writer thread.
     * Must be called before [onFrame].
     */
    fun open(file: File) {
        writer =
            FileWriter(file).apply {
                write("frame_index,timestamp_ns\n")
                flush()
            }
        isRunning = true
        writerThread =
            Thread({
                val w = writer ?: return@Thread
                while (isRunning || !queue.isEmpty()) {
                    val entry = queue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                    val (index, timestampNs) = entry
                    w.write("$index,$timestampNs\n")
                    framesSinceFlush++
                    if (framesSinceFlush >= 30) {
                        w.flush()
                        framesSinceFlush = 0
                    }
                }
            }, "FrameTimestampWriter").apply { start() }
    }

    /**
     * Records a frame with the given [timestampNs] (nanoseconds).
     * The CSV line is enqueued for background writing.
     * If the queue is full, the entry is dropped (lossy backpressure).
     */
    fun onFrame(timestampNs: Long) {
        val index = frameCount
        if (frameCount == 0) {
            firstFrameNs = timestampNs
        }
        lastFrameNs = timestampNs
        frameCount++

        if (!queue.offer(index to timestampNs)) {
            // Queue full — entry dropped (lossy backpressure)
        }
    }

    /**
     * Flushes pending writes and closes the file.
     * Signals the writer thread to stop, waits for queue drain.
     */
    fun close() {
        isRunning = false
        writerThread?.join(5000L)
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
