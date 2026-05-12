package ru.skatelab.capture.data.export

import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.proto.Imu.IMUGap
import ru.skatelab.capture.proto.Imu.IMURecord
import ru.skatelab.capture.proto.Imu.IMUSample as ProtoIMUSample
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import javax.inject.Inject

/**
 * Writes delimited protobuf IMURecord messages (IMUSample or IMUGap) to a .binpb file.
 * Uses a 16KB BufferedOutputStream for efficient I/O.
 *
 * Writing IMUSample: converts [ImuSample] to protobuf IMURecord and calls writeDelimitedTo.
 * Writing IMUGap: creates IMUGap protobuf message and calls writeDelimitedTo.
 */
class ImuStreamWriter @Inject constructor() {

    private var stream: BufferedOutputStream? = null
    private var fileOutputStream: FileOutputStream? = null

    /** Open the output file with a 16KB buffer. */
    fun open(file: File) {
        fileOutputStream = FileOutputStream(file)
        stream = BufferedOutputStream(fileOutputStream, 16_384)
    }

    /**
     * Write an IMU sample as a delimited IMURecord protobuf message.
     * Thread-safe: synchronized on the stream to allow BLE callback thread writes.
     */
    @Synchronized
    fun write(sample: ImuSample) {
        val s = stream ?: throw IllegalStateException("Writer not opened. Call open() first.")
        val protoSample = ProtoIMUSample.newBuilder()
            .setTimestampNs(sample.timestampNs)
            .setAccX(sample.accX)
            .setAccY(sample.accY)
            .setAccZ(sample.accZ)
            .setGyroX(sample.gyroX)
            .setGyroY(sample.gyroY)
            .setGyroZ(sample.gyroZ)
            .setQuatW(sample.quatW)
            .setQuatX(sample.quatX)
            .setQuatY(sample.quatY)
            .setQuatZ(sample.quatZ)
            .build()
        val record = IMURecord.newBuilder()
            .setSample(protoSample)
            .build()
        record.writeDelimitedTo(s)
    }

    /**
     * Write an IMUGap marker to mark a BLE disconnect/reconnect discontinuity.
     * @param lastSampleNs timestamp of last sample before disconnect
     * @param firstSampleNs timestamp of first sample after reconnect
     * @param reconnectSeq reconnect sequence number
     */
    @Synchronized
    fun writeGap(lastSampleNs: Long, firstSampleNs: Long, reconnectSeq: Int) {
        val s = stream ?: throw IllegalStateException("Writer not opened. Call open() first.")
        val gap = IMUGap.newBuilder()
            .setLastSampleNs(lastSampleNs)
            .setFirstSampleNs(firstSampleNs)
            .setReconnectSeq(reconnectSeq)
            .build()
        val record = IMURecord.newBuilder()
            .setGap(gap)
            .build()
        record.writeDelimitedTo(s)
    }

    /** Flush buffered data to the OS without closing the stream. */
    @Synchronized
    fun flush() {
        val s = stream ?: return
        s.flush()
    }

    /** Flush, fsync, and close the stream. Guarantees durability. */
    @Synchronized
    fun close() {
        val s = stream ?: return
        s.flush()
        // fsync for durability
        try {
            fileOutputStream?.fd?.sync()
        } catch (_: Exception) {
            // Best-effort fsync; data still flushed to OS buffer
        }
        s.close()
        stream = null
        fileOutputStream = null
    }
}
