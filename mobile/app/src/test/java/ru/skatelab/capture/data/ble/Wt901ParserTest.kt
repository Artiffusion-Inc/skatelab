package ru.skatelab.capture.data.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

class Wt901ParserTest {

    private lateinit var parser: Wt901Parser

    @Before
    fun setUp() {
        parser = Wt901Parser()
    }

    // --- Helper: build a valid WT901 frame ---

    /** Build a complete 11-byte frame with correct checksum. */
    private fun buildFrame(type: Byte, data: ByteArray): ByteArray {
        require(data.size == 8) { "Data payload must be 8 bytes (4x int16)" }
        val frame = ByteArray(11)
        frame[0] = 0x55.toByte() // header
        frame[1] = type
        System.arraycopy(data, 0, frame, 2, 8)
        // Checksum = sum of bytes[0..9] & 0xFF
        var sum = 0
        for (i in 0 until 10) {
            sum += frame[i].toInt() and 0xFF
        }
        frame[10] = (sum and 0xFF).toByte()
        return frame
    }

    /** Write a signed 16-bit LE value into a byte array at the given offset. */
    private fun writeInt16LE(buf: ByteArray, offset: Int, value: Short) {
        buf[offset] = (value.toInt() and 0xFF).toByte()
        buf[offset + 1] = (value.toInt() shr 8 and 0xFF).toByte()
    }

    // --- Test 1: Complete 0x51 acceleration frame parsing ---

    @Test
    fun parseCompleteAccelerationFrame() {
        val data = ByteArray(8)
        // ax=1g (scaled value = 32768/16 * 1 = 2048), ay=0, az=0, temp=0
        writeInt16LE(data, 0, 2048) // ax ≈ 1g
        writeInt16LE(data, 2, 0)    // ay = 0
        writeInt16LE(data, 4, 0)    // az = 0
        writeInt16LE(data, 6, 0)    // temperature

        val frame = buildFrame(0x51, data)

        // Feed only acceleration frame — bitmask incomplete → no sample emitted
        val result = parser.feed(frame, 1_000_000_000L)
        assertNull("Single ACC frame should not produce ImuSample", result)
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 2: Complete IMU sample from 3 frames (0x51 + 0x52 + 0x59) ---

    @Test
    fun parseCompleteImuSampleFromThreeFrames() {
        val t0 = 1_000_000_000L

        // ACC frame: ax=2048 (~1g), ay=0, az=0
        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        writeInt16LE(accData, 2, 0)
        writeInt16LE(accData, 4, 0)
        writeInt16LE(accData, 6, 0)
        val accFrame = buildFrame(0x51, accData)

        // GYRO frame: gx=16384 (~1000°/s), gy=0, gz=0
        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 16384)
        writeInt16LE(gyroData, 2, 0)
        writeInt16LE(gyroData, 4, 0)
        writeInt16LE(gyroData, 6, 0)
        val gyroFrame = buildFrame(0x52, gyroData)

        // QUAT frame: qw=32767 (~1.0), qx=0, qy=0, qz=0
        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 32767) // qw ≈ 1.0
        writeInt16LE(quatData, 2, 0)
        writeInt16LE(quatData, 4, 0)
        writeInt16LE(quatData, 6, 0)
        val quatFrame = buildFrame(0x59, quatData)

        // Feed all three in one BLE notification (33 bytes)
        val combined = accFrame + gyroFrame + quatFrame
        val result = parser.feed(combined, t0)

        assertNotNull("Three complete frames should produce ImuSample", result)
        result!!.let { sample ->
            assertEquals(t0, sample.timestampNs)
            // ACC: 2048 * 16 * 9.80665 / 32768 ≈ 9.81 m/s²
            assertEquals(9.81f, sample.accX, 0.1f)
            assertEquals(0f, sample.accY, 0.01f)
            assertEquals(0f, sample.accZ, 0.01f)
            // GYRO: 16384 * 2000/32768 = 1000.0
            assertEquals(1000.0f, sample.gyroX, 1.0f)
            assertEquals(0f, sample.gyroY, 0.01f)
            assertEquals(0f, sample.gyroZ, 0.01f)
            // QUAT: 32767 * 1/32768 ≈ 0.99997
            assertEquals(1.0f, sample.quatW, 0.001f)
            assertEquals(0f, sample.quatX, 0.001f)
            assertEquals(0f, sample.quatY, 0.001f)
            assertEquals(0f, sample.quatZ, 0.001f)
        }
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 3: Partial frame across two BLE notifications ---

    @Test
    fun parsePartialFrameAcrossTwoNotifications() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        writeInt16LE(accData, 2, 0)
        writeInt16LE(accData, 4, 0)
        writeInt16LE(accData, 6, 0)
        val accFrame = buildFrame(0x51, accData)

        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 1000)
        writeInt16LE(gyroData, 2, 0)
        writeInt16LE(gyroData, 4, 0)
        writeInt16LE(gyroData, 6, 0)
        val gyroFrame = buildFrame(0x52, gyroData)

        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 16384)
        writeInt16LE(quatData, 2, 0)
        writeInt16LE(quatData, 4, 0)
        writeInt16LE(quatData, 6, 0)
        val quatFrame = buildFrame(0x59, quatData)

        // First notification: acc frame (11 bytes) + first 9 bytes of gyro frame
        val firstPart = accFrame + gyroFrame.copyOfRange(0, 9)
        val result1 = parser.feed(firstPart, t0)
        assertNull("Partial gyro frame should not produce sample", result1)

        // Second notification: remaining 2 bytes of gyro + complete quat frame
        val secondPart = gyroFrame.copyOfRange(9, 11) + quatFrame
        val result2 = parser.feed(secondPart, t0 + 5_000_000L)
        assertNotNull("Remaining gyro + quat should complete the sample", result2)
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 4: Invalid checksum rejection ---

    @Test
    fun rejectInvalidChecksum() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        val accFrame = buildFrame(0x51, accData)

        // Corrupt the checksum byte
        val corrupted = accFrame.copyOf()
        corrupted[10] = (corrupted[10].toInt() xor 0xFF).toByte()

        val result = parser.feed(corrupted, t0)
        assertNull("Corrupted checksum should not produce sample", result)
    }

    // --- Test 5: 0x55 in payload rejection ---

    @Test
    fun rejectHeaderByteInPayload() {
        val t0 = 1_000_000_000L

        // Build an ACC frame with 0x55 in the data payload area
        val accData = ByteArray(8)
        accData[0] = 0x55.toByte() // This creates a false header in payload
        accData[1] = 0x51.toByte() // And a false type byte
        writeInt16LE(accData, 2, 0)
        writeInt16LE(accData, 4, 0)
        writeInt16LE(accData, 6, 0)

        val frame = buildFrame(0x51, accData)
        // The frame is valid (checksum covers the 0x55 in payload)
        // When the parser scans for 0x55, it might hit the one in the data area first.
        // But that won't form a valid frame because the checksum will fail.
        // The parser should eventually find the real header at byte 0.

        // Actually, let's construct a scenario where a stray 0x55 appears
        // before the real frame in a BLE notification.
        val stray = byteArrayOf(0x55.toByte(), 0x51.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF.toByte())
        // Checksum for this stray frame is wrong (0x55+0x51=0xA6, not 0xFF)
        val validFrame = buildFrame(0x51, ByteArray(8).also { writeInt16LE(it, 0, 2048) })

        val combined = stray + validFrame
        val result = parser.feed(combined, t0)
        // The stray 0x55 should fail checksum, then the real frame should parse
        // But we still won't get a complete ImuSample (only ACC received)
        assertNull("Only ACC frame, not a complete sample", result)
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 6: Duplicate frame type drops cycle ---

    @Test
    fun duplicateFrameTypeDropsIncompleteCycle() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        writeInt16LE(accData, 2, 0)
        writeInt16LE(accData, 4, 0)
        writeInt16LE(accData, 6, 0)
        val accFrame = buildFrame(0x51, accData)

        // Feed first ACC frame
        val result1 = parser.feed(accFrame, t0)
        assertNull(result1)

        // Feed second ACC frame (duplicate) — should drop incomplete cycle
        val result2 = parser.feed(accFrame, t0 + 5_000_000L)
        assertNull("Duplicate ACC should not produce sample", result2)
        assertEquals("Dropped partial count should be 1", 1, parser.droppedPartialCount)

        // Now feed GYRO + QUAT — with the second ACC as the start of a new cycle,
        // we should get a complete sample
        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 1000)
        writeInt16LE(gyroData, 2, 0)
        writeInt16LE(gyroData, 4, 0)
        writeInt16LE(gyroData, 6, 0)
        val gyroFrame = buildFrame(0x52, gyroData)

        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 16384)
        writeInt16LE(quatData, 2, 0)
        writeInt16LE(quatData, 4, 0)
        writeInt16LE(quatData, 6, 0)
        val quatFrame = buildFrame(0x59, quatData)

        val combined = gyroFrame + quatFrame
        val result3 = parser.feed(combined, t0 + 10_000_000L)
        assertNotNull("ACC + GYRO + QUAT should complete after duplicate reset", result3)
    }

    // --- Test 7: 15ms timeout drops incomplete cycle ---

    @Test
    fun timeoutDropsIncompleteCycle() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        val accFrame = buildFrame(0x51, accData)

        // Feed ACC at t0
        parser.feed(accFrame, t0)
        assertEquals(0, parser.droppedPartialCount)

        // Feed nothing for 20ms — next feed triggers timeout
        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 1000)
        val gyroFrame = buildFrame(0x52, gyroData)

        // Feed GYRO 20ms later — exceeds 15ms timeout
        parser.feed(gyroFrame, t0 + 20_000_000L)
        assertEquals("Timeout should increment dropped partial count", 1, parser.droppedPartialCount)

        // Now we're in a new cycle with GYRO. Feed ACC + QUAT to complete it.
        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 16384)
        val quatFrame = buildFrame(0x59, quatData)

        val combined = accFrame + quatFrame
        val result = parser.feed(combined, t0 + 25_000_000L)
        assertNotNull("New cycle after timeout should complete normally", result)
    }
}
