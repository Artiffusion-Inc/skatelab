package ru.skatelab.capture.data.ble

import android.os.SystemClock
import android.util.Log
import kotlin.math.cos
import kotlin.math.sin
import ru.skatelab.capture.domain.model.ImuSample

/** Result of a register read (0x71 frame). */
data class RegisterReadResult(val register: Int, val data: ShortArray) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is RegisterReadResult) return false
        return register == other.register && data.contentEquals(other.data)
    }

    override fun hashCode(): Int = 31 * register + data.contentHashCode()
}

/**
 * Parses WT901 BLE frames into [ImuSample].
 *
 * Handles two frame formats:
 * - Individual frames (0x51 ACC, 0x52 GYRO, 0x59 Quaternion): 11 bytes each
 * - Combined frame (0x61): 20 bytes — ACC+GYRO+Euler angles, no checksum
 * - Register read response (0x71): 20 bytes — register address + 8x int16 data, no checksum
 *
 * Also handles:
 * - Partial frames spanning BLE notifications (buffer accumulation)
 * - Checksum validation for individual frames (rejects false 0x55 headers)
 * - Bitmask sample grouping for individual frames
 * - Euler-to-quaternion conversion for combined frames
 *
 * Based on XAMLCORP PacketParser.cs.
 */
class Wt901Parser {
    companion object {
        // Frame headers
        private const val FRAME_HEADER: Byte = 0x55
        private const val TYPE_ACC: Byte = 0x51
        private const val TYPE_GYRO: Byte = 0x52
        private const val TYPE_QUAT: Byte = 0x59
        private const val TYPE_COMBINED: Byte = 0x61
        private const val TYPE_REG_READ: Byte = 0x71

        // Frame sizes
        private const val INDIVIDUAL_FRAME_SIZE = 11
        private const val COMBINED_FRAME_SIZE = 20
        private const val REG_READ_FRAME_SIZE = 20

        // Bitmask for individual-frame sample grouping
        private const val BIT_ACC = 0x01
        private const val BIT_GYRO = 0x02
        private const val BIT_QUAT = 0x04
        private const val BIT_COMPLETE = 0x07

        // Scale factors (XAMLCORP SDK)
        private const val SCALE_ACC = 16f * 9.80665f / 32768f // ±16g → m/s²
        private const val SCALE_GYRO = 2000f / 32768f // ±2000°/s
        private const val SCALE_ANGLE = 180f / 32768f // ±180°
        private const val SCALE_QUAT = 1f / 32768f

        // Plausibility limits for 0x61 frame sync validation
        // Raw int16 range for ±16g ACC: |raw| ≤ 32767 → ~157 m/s²
        // Raw int16 range for ±2000°/s GYRO: |raw| ≤ 32767
        // But real skating values: ACC ≤ 50g raw ≈ 25000, GYRO ≤ 3600°/s raw ≈ 29500
        private const val ACC_RAW_LIMIT = 31000 // ~15g, well above any real value
        private const val GYRO_RAW_LIMIT = 32000 // ~1953°/s, well above any real value

        // Timeout for incomplete individual-frame cycle
        private const val CYCLE_TIMEOUT_NS = 15_000_000L // 15ms
    }

    // Buffer for partial frames across BLE notifications
    private val buffer = ByteArray(512)
    private var bufferSize = 0
    private var droppedByteCount = 0L

    // Individual-frame bitmask grouping state
    private var receivedMask = 0
    private var cycleStartNs = 0L
    private var accX = 0f
    private var accY = 0f
    private var accZ = 0f
    private var gyroX = 0f
    private var gyroY = 0f
    private var gyroZ = 0f
    private var quatW = 0f
    private var quatX = 0f
    private var quatY = 0f
    private var quatZ = 0f
    private var sampleTimestampNs = 0L

    // Frame type statistics for debugging
    private var frameCounts = mutableMapOf<Byte, Int>()
    var logTag: String = "Wt901Parse"
    private var logSeq = 0

    /** Count of incomplete cycles dropped. */
    var droppedPartialCount = 0
        private set

    /** Callback invoked when a 0x71 register read response is parsed. */
    var onRegisterRead: ((RegisterReadResult) -> Unit)? = null

    /**
     * Feed incoming BLE notification bytes and attempt to parse.
     *
     * A single BLE notification may contain multiple frames (e.g. 4× 20-byte 0x61
     * when MTU > 20). All parsed samples are returned.
     *
     * @param bytes Raw bytes from BLE notification.
     * @param arrivalNs Monotonic timestamp from [SystemClock.elapsedRealtimeNanos].
     * @return List of [ImuSample]s parsed from this notification (may be empty).
     */
    fun feed(
        bytes: ByteArray,
        arrivalNs: Long,
    ): List<ImuSample> {
        appendToBuffer(bytes)

        // Check individual-frame cycle timeout
        if (receivedMask != 0 && receivedMask != BIT_COMPLETE) {
            if (arrivalNs - cycleStartNs > CYCLE_TIMEOUT_NS) {
                droppedPartialCount++
                resetCycle()
            }
        }

        // Parse all complete frames in the buffer
        val samples = mutableListOf<ImuSample>()
        while (bufferSize >= INDIVIDUAL_FRAME_SIZE) {
            val headerIdx = findFrameHeader()
            if (headerIdx < 0) {
                bufferSize = 0
                break
            }

            if (headerIdx > 0) {
                shiftBuffer(headerIdx)
            }

            val frameType = buffer[1]

            // Track frame types for debugging
            frameCounts[frameType] = (frameCounts[frameType] ?: 0) + 1
            logSeq++
            // Log raw 0x61 frame bytes on first occurrence and every 5000th
            if (frameType == TYPE_COMBINED && (frameCounts[frameType] == 1 || frameCounts[frameType]!! % 5000 == 0)) {
                val rawHex =
                    (0 until minOf(COMBINED_FRAME_SIZE, bufferSize)).joinToString(
                        " ",
                    ) { "%02X".format(buffer[it].toInt() and 0xFF) }
                Log.i(logTag, "RAW 0x61 frame #${frameCounts[frameType]}: $rawHex")
            }
            if (logSeq % 200 == 0) {
                val stats =
                    frameCounts.entries.joinToString(", ") { (k, v) ->
                        "0x%02X=%d".format(k, v)
                    }
                Log.i(logTag, "Frame stats: $stats, dropped=$droppedPartialCount, mask=$receivedMask")
            }

            // Determine frame size
            val frameSize =
                when (frameType) {
                    TYPE_COMBINED -> COMBINED_FRAME_SIZE
                    TYPE_REG_READ -> REG_READ_FRAME_SIZE
                    else -> INDIVIDUAL_FRAME_SIZE
                }
            if (bufferSize < frameSize) {
                break // Wait for more data
            }

            // Validate checksum for individual frames; combined and register-read frames have no checksum
            when (frameType) {
                TYPE_COMBINED -> {
                    if (!isCombinedFramePlausible()) {
                        Log.w(logTag, "0x61 frame failed plausibility check — desync likely, skipping 1 byte")
                        shiftBuffer(1)
                        continue
                    }
                }
                TYPE_REG_READ -> {
                    // 0x71 frames in BLE mode have no checksum
                }
                else -> {
                    if (!isChecksumValid()) {
                        shiftBuffer(1)
                        continue
                    }
                }
            }

            val sample =
                when (frameType) {
                    TYPE_COMBINED -> parseCombinedFrame(arrivalNs)
                    TYPE_ACC, TYPE_GYRO, TYPE_QUAT -> processFrame(frameType, arrivalNs)
                    TYPE_REG_READ -> {
                        parseRegisterReadFrame()
                        null
                    }
                    else -> {
                        shiftBuffer(1)
                        continue
                    }
                }

            if (sample != null) {
                samples.add(sample)
            }

            shiftBuffer(frameSize)
        }

        return samples
    }

    /** Reset parser state. Call on disconnect/reconnect to clear all internal state. */
    fun reset() {
        bufferSize = 0
        droppedByteCount = 0L
        frameCounts.clear()
        logSeq = 0
        droppedPartialCount = 0
        resetCycle()
    }

    private fun resetCycle() {
        receivedMask = 0
        cycleStartNs = 0L
        accX = 0f
        accY = 0f
        accZ = 0f
        gyroX = 0f
        gyroY = 0f
        gyroZ = 0f
        quatW = 0f
        quatX = 0f
        quatY = 0f
        quatZ = 0f
        sampleTimestampNs = 0L
    }

    private fun appendToBuffer(bytes: ByteArray) {
        val available = buffer.size - bufferSize
        if (bytes.size > available) {
            val dropped = bytes.size - available
            droppedByteCount += dropped
            if (droppedByteCount % 100 == 0L || dropped > 20) {
                Log.w(
                    logTag,
                    "Buffer overflow: dropped $dropped bytes (total=$droppedByteCount), incoming=${bytes.size} available=$available",
                )
            }
        }
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

    /**
     * Plausibility check for 0x61 combined frames (no checksum in protocol).
     * Validates that ACC and GYRO raw int16 values are within physically plausible ranges.
     * Returns false if any value exceeds limits — likely frame desync.
     */
    private fun isCombinedFramePlausible(): Boolean {
        // ACC raw: bytes 2-7, physically |raw| ≤ 31000 (~15g)
        for (i in intArrayOf(2, 4, 6)) {
            val raw = readInt16Raw(i)
            if (kotlin.math.abs(raw) > ACC_RAW_LIMIT) return false
        }
        // GYRO raw: bytes 8-13, physically |raw| ≤ 32000 (~1953°/s)
        for (i in intArrayOf(8, 10, 12)) {
            val raw = readInt16Raw(i)
            if (kotlin.math.abs(raw) > GYRO_RAW_LIMIT) return false
        }
        return true
    }

    /** Read signed 16-bit LE from buffer at offset (raw, no scaling). */
    private fun readInt16Raw(offset: Int): Int {
        val raw = ((buffer[offset + 1].toInt() and 0xFF) shl 8) or (buffer[offset].toInt() and 0xFF)
        return raw.toShort().toInt() // sign-extend via Short
    }

    /** Checksum: sum of bytes[0..9] & 0xFF must equal bytes[10]. */
    private fun isChecksumValid(): Boolean {
        var sum = 0
        for (i in 0 until INDIVIDUAL_FRAME_SIZE - 1) {
            sum += buffer[i].toInt() and 0xFF
        }
        return (sum and 0xFF) == (buffer[INDIVIDUAL_FRAME_SIZE - 1].toInt() and 0xFF)
    }

    /**
     * Parse 0x61 combined frame (20 bytes).
     * Layout: [0x55][0x61][AccX][AccY][AccZ][GyrX][GyrY][GyrZ][Roll][Pitch][Yaw]
     * No checksum. Euler angles converted to quaternion.
     */
    private fun parseCombinedFrame(arrivalNs: Long): ImuSample {
        val aX = readInt16LE(2) * SCALE_ACC
        val aY = readInt16LE(4) * SCALE_ACC
        val aZ = readInt16LE(6) * SCALE_ACC
        val gX = readInt16LE(8) * SCALE_GYRO
        val gY = readInt16LE(10) * SCALE_GYRO
        val gZ = readInt16LE(12) * SCALE_GYRO
        val roll = readInt16LE(14) * SCALE_ANGLE // degrees
        val pitch = readInt16LE(16) * SCALE_ANGLE // degrees
        val yaw = readInt16LE(18) * SCALE_ANGLE // degrees

        // Euler (ZYX intrinsic) → quaternion
        val q = eulerToQuaternion(roll, pitch, yaw)

        return ImuSample(
            timestampNs = arrivalNs,
            accX = aX, accY = aY, accZ = aZ,
            gyroX = gX, gyroY = gY, gyroZ = gZ,
            quatW = q[0], quatX = q[1], quatY = q[2], quatZ = q[3],
        )
    }

    /**
     * Convert Euler angles (degrees, ZYX intrinsic rotation) to quaternion [w, x, y, z].
     * WT901 convention: Roll=X, Pitch=Y, Yaw=Z.
     */
    private fun eulerToQuaternion(
        rollDeg: Float,
        pitchDeg: Float,
        yawDeg: Float,
    ): FloatArray {
        val roll = Math.toRadians(rollDeg.toDouble())
        val pitch = Math.toRadians(pitchDeg.toDouble())
        val yaw = Math.toRadians(yawDeg.toDouble())

        val cr = cos(roll / 2)
        val sr = sin(roll / 2)
        val cp = cos(pitch / 2)
        val sp = sin(pitch / 2)
        val cy = cos(yaw / 2)
        val sy = sin(yaw / 2)

        val w = (cr * cp * cy + sr * sp * sy).toFloat()
        val x = (sr * cp * cy - cr * sp * sy).toFloat()
        val y = (cr * sp * cy + sr * cp * sy).toFloat()
        val z = (cr * cp * sy - sr * sp * cy).toFloat()

        return floatArrayOf(w, x, y, z)
    }

    /**
     * Process an individual frame (0x51/0x52/0x59). Returns [ImuSample]
     * when bitmask complete, or null.
     */
    private fun processFrame(
        frameType: Byte,
        arrivalNs: Long,
    ): ImuSample? {
        val bit =
            when (frameType) {
                TYPE_ACC -> BIT_ACC
                TYPE_GYRO -> BIT_GYRO
                TYPE_QUAT -> BIT_QUAT
                else -> return null
            }

        // Duplicate frame type in current cycle → drop previous incomplete
        if (receivedMask and bit != 0) {
            droppedPartialCount++
            resetCycle()
        }

        if (receivedMask == 0) {
            cycleStartNs = arrivalNs
            sampleTimestampNs = arrivalNs
        }

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

        return if (receivedMask == BIT_COMPLETE) {
            val sample =
                ImuSample(
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

    /**
     * Parse 0x71 register read response frame (20 bytes in BLE mode).
     * Layout: [0x55][0x71][RegL][RegH][d0L][d0H]...[d7L][d7H]
     * No checksum. 8 consecutive register values as int16 LE.
     */
    private fun parseRegisterReadFrame() {
        val reg = buffer[2].toInt() and 0xFF
        val data = ShortArray(8) { i -> readInt16LEShort(4 + i * 2) }
        onRegisterRead?.invoke(RegisterReadResult(reg, data))
    }

    /** Read a signed 16-bit little-endian value from buffer at offset, return as Short. */
    private fun readInt16LEShort(offset: Int): Short {
        val low = buffer[offset].toInt() and 0xFF
        val high = buffer[offset + 1].toInt() and 0xFF
        return ((high shl 8) or low).toShort()
    }

    /** Read a signed 16-bit little-endian value from buffer at offset, return as Float. */
    private fun readInt16LE(offset: Int): Float {
        val low = buffer[offset].toInt() and 0xFF
        val high = buffer[offset + 1].toInt() and 0xFF
        return ((high shl 8) or low).toShort().toFloat()
    }
}
