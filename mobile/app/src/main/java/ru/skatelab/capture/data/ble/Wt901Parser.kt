package ru.skatelab.capture.data.ble

import android.os.SystemClock
import ru.skatelab.capture.domain.model.ImuSample

/**
 * Parses WT901 BLE individual-frame mode (0x51/0x52/0x59) into [ImuSample].
 *
 * Handles:
 * - Partial frames spanning BLE notifications (buffer accumulation)
 * - Checksum validation (rejects false 0x55 headers in payload)
 * - Bitmask sample grouping: ACC=0x01, GYRO=0x02, QUAT=0x04, COMPLETE=0x07
 * - Duplicate frame type detection → drops previous incomplete cycle
 * - 15ms timeout → drops incomplete cycle
 *
 * Based on XAMLCORP PacketParser.cs buffer accumulation pattern.
 */
class Wt901Parser {

    companion object {
        // Frame types
        private const val FRAME_HEADER: Byte = 0x55
        private const val TYPE_ACC: Byte = 0x51
        private const val TYPE_GYRO: Byte = 0x52
        private const val TYPE_QUAT: Byte = 0x59

        // Frame sizes (header + type + data + checksum)
        private const val FRAME_SIZE = 11

        // Bitmask for sample grouping
        private const val BIT_ACC = 0x01
        private const val BIT_GYRO = 0x02
        private const val BIT_QUAT = 0x04
        private const val BIT_COMPLETE = 0x07

        // Scale factors
        private const val SCALE_ACC = 16f / 32768f   // ±16g
        private const val SCALE_GYRO = 2000f / 32768f // ±2000°/s
        private const val SCALE_QUAT = 1f / 32768f

        // Timeout for incomplete cycle: 1.5× the 10ms expected interval at 100Hz
        private const val CYCLE_TIMEOUT_NS = 15_000_000L // 15ms
    }

    // Buffer for partial frames across BLE notifications
    private val buffer = ByteArray(64)
    private var bufferSize = 0

    // Bitmask sample grouping state
    private var receivedMask = 0
    private var cycleStartNs = 0L

    // Accumulated values for current cycle
    private var accX = 0f; private var accY = 0f; private var accZ = 0f
    private var gyroX = 0f; private var gyroY = 0f; private var gyroZ = 0f
    private var quatW = 0f; private var quatX = 0f; private var quatY = 0f; private var quatZ = 0f
    private var sampleTimestampNs = 0L

    /** Count of incomplete cycles dropped due to timeout or duplicate frame type. */
    var droppedPartialCount = 0
        private set

    /**
     * Feed incoming BLE notification bytes and attempt to parse.
     *
     * @param bytes Raw bytes from BLE notification (typically 20 bytes).
     * @param arrivalNs Monotonic timestamp from [SystemClock.elapsedRealtimeNanos].
     * @return A complete [ImuSample] if all three frame types were received in the cycle,
     *         or null if the cycle is incomplete.
     */
    fun feed(bytes: ByteArray, arrivalNs: Long): ImuSample? {
        appendToBuffer(bytes)

        // Check for cycle timeout before parsing new data
        if (receivedMask != 0 && receivedMask != BIT_COMPLETE) {
            if (arrivalNs - cycleStartNs > CYCLE_TIMEOUT_NS) {
                droppedPartialCount++
                resetCycle()
            }
        }

        // Parse all complete frames in the buffer
        var result: ImuSample? = null
        while (bufferSize >= FRAME_SIZE) {
            val headerIdx = findFrameHeader()
            if (headerIdx < 0) {
                // No 0x55 found — discard all buffered bytes
                bufferSize = 0
                break
            }

            if (headerIdx > 0) {
                // Discard bytes before the header
                shiftBuffer(headerIdx)
            }

            if (bufferSize < FRAME_SIZE) {
                // Not enough data for a complete frame — wait for more
                break
            }

            val frameType = buffer[1]

            // Validate checksum before processing
            if (!isChecksumValid()) {
                // Checksum invalid — 0x55 was in payload, not a real header.
                // Advance past this false header and keep scanning.
                shiftBuffer(1)
                continue
            }

            // Valid frame — process it
            val sample = processFrame(frameType, arrivalNs)
            if (sample != null) {
                result = sample
            }

            // Remove processed frame from buffer
            shiftBuffer(FRAME_SIZE)
        }

        return result
    }

    /** Reset parser state for a new cycle. Call when discarding incomplete samples. */
    fun reset() {
        bufferSize = 0
        resetCycle()
    }

    private fun resetCycle() {
        receivedMask = 0
        cycleStartNs = 0L
        accX = 0f; accY = 0f; accZ = 0f
        gyroX = 0f; gyroY = 0f; gyroZ = 0f
        quatW = 0f; quatX = 0f; quatY = 0f; quatZ = 0f
        sampleTimestampNs = 0L
    }

    private fun appendToBuffer(bytes: ByteArray) {
        val available = buffer.size - bufferSize
        val toCopy = minOf(bytes.size, available)
        System.arraycopy(bytes, 0, buffer, bufferSize, toCopy)
        bufferSize += toCopy
    }

    private fun findFrameHeader(): Int {
        for (i in 0 until bufferSize) {
            if (buffer[i] == FRAME_HEADER) return i
        }
        return -1
    }

    private fun shiftBuffer(dropCount: Int) {
        val remaining = bufferSize - dropCount
        if (remaining > 0) {
            System.arraycopy(buffer, dropCount, buffer, 0, remaining)
        }
        bufferSize = remaining
    }

    /** Checksum: sum of bytes[0..9] & 0xFF must equal bytes[10]. */
    private fun isChecksumValid(): Boolean {
        var sum = 0
        for (i in 0 until FRAME_SIZE - 1) {
            sum += buffer[i].toInt() and 0xFF
        }
        return (sum and 0xFF) == (buffer[FRAME_SIZE - 1].toInt() and 0xFF)
    }

    /**
     * Process a validated frame. Returns [ImuSample] when the bitmask is complete,
     * or null if the cycle is still incomplete.
     */
    private fun processFrame(frameType: Byte, arrivalNs: Long): ImuSample? {
        val bit = when (frameType) {
            TYPE_ACC -> BIT_ACC
            TYPE_GYRO -> BIT_GYRO
            TYPE_QUAT -> BIT_QUAT
            else -> return null // Unknown frame type — skip
        }

        // Check for duplicate frame type in current cycle
        if (receivedMask and bit != 0) {
            // Duplicate — drop previous incomplete cycle, start new one with this frame
            droppedPartialCount++
            resetCycle()
        }

        // First frame of cycle starts the timer
        if (receivedMask == 0) {
            cycleStartNs = arrivalNs
            sampleTimestampNs = arrivalNs
        }

        // Parse frame data
        when (frameType) {
            TYPE_ACC -> {
                accX = readInt16LE(2) * SCALE_ACC
                accY = readInt16LE(4) * SCALE_ACC
                accZ = readInt16LE(6) * SCALE_ACC
            }
            TYPE_GYRO -> {
                gyroX = readInt16LE(2) * SCALE_GYRO
                gyroY = readInt16LE(4) * SCALE_GYRO
                gyroZ = readInt16LE(6) * SCALE_GYRO
            }
            TYPE_QUAT -> {
                quatW = readInt16LE(2) * SCALE_QUAT
                quatX = readInt16LE(4) * SCALE_QUAT
                quatY = readInt16LE(6) * SCALE_QUAT
                quatZ = readInt16LE(8) * SCALE_QUAT
            }
        }

        receivedMask = receivedMask or bit

        // Complete cycle — emit sample
        return if (receivedMask == BIT_COMPLETE) {
            val sample = ImuSample(
                timestampNs = sampleTimestampNs,
                accX = accX, accY = accY, accZ = accZ,
                gyroX = gyroX, gyroY = gyroY, gyroZ = gyroZ,
                quatW = quatW, quatX = quatX, quatY = quatY, quatZ = quatZ,
            )
            resetCycle()
            sample
        } else {
            null
        }
    }

    /** Read a signed 16-bit little-endian value from the buffer at the given offset. */
    private fun readInt16LE(offset: Int): Float {
        val low = buffer[offset].toInt() and 0xFF
        val high = buffer[offset + 1].toInt() and 0xFF
        return ((high shl 8) or low).toShort().toFloat()
    }
}
