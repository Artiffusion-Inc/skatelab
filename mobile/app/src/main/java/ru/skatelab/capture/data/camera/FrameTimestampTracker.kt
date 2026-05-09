package ru.skatelab.capture.data.camera

import java.io.File
import java.io.FileWriter
import javax.inject.Inject

class FrameTimestampTracker @Inject constructor() {
    private var writer: FileWriter? = null
    private var frameIndex = 0
    private var firstFrameNs = 0L
    private var lastFrameNs = 0L

    fun open(file: File) {
        file.parentFile?.mkdirs()
        writer = FileWriter(file)
        writer?.append("frame_index,timestamp_ns\n")
        frameIndex = 0
        firstFrameNs = 0L
        lastFrameNs = 0L
    }

    fun onFrame(timestampNs: Long) {
        if (firstFrameNs == 0L) firstFrameNs = timestampNs
        lastFrameNs = timestampNs
        writer?.append("$frameIndex,$timestampNs\n")
        frameIndex++
    }

    fun close() {
        writer?.close()
        writer = null
    }

    fun getFrameCount(): Int = frameIndex
    fun getFirstFrameNs(): Long = firstFrameNs
    fun getLastFrameNs(): Long = lastFrameNs

    fun computeFps(): Int {
        if (frameIndex < 2 || firstFrameNs == lastFrameNs) return 0
        val durationNs = lastFrameNs - firstFrameNs
        return Math.round((frameIndex - 1) * 1_000_000_000.0 / durationNs).toInt()
    }
}
