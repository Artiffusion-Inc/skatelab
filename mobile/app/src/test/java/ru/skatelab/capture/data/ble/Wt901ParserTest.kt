package ru.skatelab.capture.data.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
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
    private fun buildFrame(
        type: Byte,
        data: ByteArray,
    ): ByteArray {
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
    private fun writeInt16LE(
        buf: ByteArray,
        offset: Int,
        value: Short,
    ) {
        buf[offset] = (value.toInt() and 0xFF).toByte()
        buf[offset + 1] = (value.toInt() shr 8 and 0xFF).toByte()
    }

    // --- Test 1: Complete 0x51 acceleration frame parsing ---

    @Test
    fun parseCompleteAccelerationFrame() {
        val data = ByteArray(8)
        writeInt16LE(data, 0, 2048) // ax ≈ 1g
        writeInt16LE(data, 2, 0)
        writeInt16LE(data, 4, 0)
        writeInt16LE(data, 6, 0)

        val frame = buildFrame(0x51, data)

        // Feed only acceleration frame — bitmask incomplete → no sample emitted
        val result = parser.feed(frame, 1_000_000_000L)
        assertTrue("Single ACC frame should not produce ImuSample", result.isEmpty())
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 2: Complete IMU sample from 3 frames (0x51 + 0x52 + 0x59) ---

    @Test
    fun parseCompleteImuSampleFromThreeFrames() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        writeInt16LE(accData, 2, 0)
        writeInt16LE(accData, 4, 0)
        writeInt16LE(accData, 6, 0)
        val accFrame = buildFrame(0x51, accData)

        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 16384)
        writeInt16LE(gyroData, 2, 0)
        writeInt16LE(gyroData, 4, 0)
        writeInt16LE(gyroData, 6, 0)
        val gyroFrame = buildFrame(0x52, gyroData)

        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 32767)
        writeInt16LE(quatData, 2, 0)
        writeInt16LE(quatData, 4, 0)
        writeInt16LE(quatData, 6, 0)
        val quatFrame = buildFrame(0x59, quatData)

        val combined = accFrame + gyroFrame + quatFrame
        val result = parser.feed(combined, t0)

        assertTrue("Three complete frames should produce ImuSample", result.isNotEmpty())
        result.first().let { sample ->
            assertEquals(t0, sample.timestampNs)
            assertEquals(9.81f, sample.accX, 0.1f)
            assertEquals(0f, sample.accY, 0.01f)
            assertEquals(0f, sample.accZ, 0.01f)
            assertEquals(1000.0f, sample.gyroX, 1.0f)
            assertEquals(0f, sample.gyroY, 0.01f)
            assertEquals(0f, sample.gyroZ, 0.01f)
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

        val firstPart = accFrame + gyroFrame.copyOfRange(0, 9)
        val result1 = parser.feed(firstPart, t0)
        assertTrue("Partial gyro frame should not produce sample", result1.isEmpty())

        val secondPart = gyroFrame.copyOfRange(9, 11) + quatFrame
        val result2 = parser.feed(secondPart, t0 + 5_000_000L)
        assertTrue("Remaining gyro + quat should complete the sample", result2.isNotEmpty())
        assertEquals(0, parser.droppedPartialCount)
    }

    // --- Test 4: Invalid checksum rejection ---

    @Test
    fun rejectInvalidChecksum() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        val accFrame = buildFrame(0x51, accData)

        val corrupted = accFrame.copyOf()
        corrupted[10] = (corrupted[10].toInt() xor 0xFF).toByte()

        val result = parser.feed(corrupted, t0)
        assertTrue("Corrupted checksum should not produce sample", result.isEmpty())
    }

    // --- Test 5: 0x55 in payload rejection ---

    @Test
    fun rejectHeaderByteInPayload() {
        val t0 = 1_000_000_000L

        val stray = byteArrayOf(0x55.toByte(), 0x51.toByte(), 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF.toByte())
        val validFrame = buildFrame(0x51, ByteArray(8).also { writeInt16LE(it, 0, 2048) })

        val combined = stray + validFrame
        val result = parser.feed(combined, t0)
        assertTrue("Only ACC frame, not a complete sample", result.isEmpty())
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

        val result1 = parser.feed(accFrame, t0)
        assertTrue(result1.isEmpty())

        val result2 = parser.feed(accFrame, t0 + 5_000_000L)
        assertTrue("Duplicate ACC should not produce sample", result2.isEmpty())
        assertEquals("Dropped partial count should be 1", 1, parser.droppedPartialCount)

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
        assertTrue("ACC + GYRO + QUAT should complete after duplicate reset", result3.isNotEmpty())
    }

    // --- Test 7: 15ms timeout drops incomplete cycle ---

    @Test
    fun timeoutDropsIncompleteCycle() {
        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        val accFrame = buildFrame(0x51, accData)

        parser.feed(accFrame, t0)
        assertEquals(0, parser.droppedPartialCount)

        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 1000)
        val gyroFrame = buildFrame(0x52, gyroData)

        parser.feed(gyroFrame, t0 + 20_000_000L)
        assertEquals("Timeout should increment dropped partial count", 1, parser.droppedPartialCount)

        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 16384)
        val quatFrame = buildFrame(0x59, quatData)

        val combined = accFrame + quatFrame
        val result = parser.feed(combined, t0 + 25_000_000L)
        assertTrue("New cycle after timeout should complete normally", result.isNotEmpty())
    }

    // --- Test 8: 0x71 register read response parsing (20-byte BLE format) ---

    /** Build a 20-byte BLE 0x71 register read frame. No checksum. */
    private fun buildRegReadFrame(
        register: Int,
        dataValues: ShortArray,
    ): ByteArray {
        require(dataValues.size == 8) { "BLE 0x71 requires exactly 8 shorts" }
        val frame = ByteArray(20)
        frame[0] = 0x55.toByte()
        frame[1] = 0x71.toByte()
        frame[2] = (register and 0xFF).toByte()
        frame[3] = ((register shr 8) and 0xFF).toByte()
        for (i in 0 until 8) {
            writeInt16LE(frame, 4 + i * 2, dataValues[i])
        }
        return frame
    }

    @Test
    fun parseRegisterReadResponse() {
        var callbackResult: RegisterReadResult? = null
        parser.onRegisterRead = { callbackResult = it }

        val dataValues = ShortArray(8)
        dataValues[0] = 780 // battery ~780 raw
        val frame = buildRegReadFrame(0x64, dataValues)

        val result = parser.feed(frame, 1_000_000_000L)

        assertTrue("0x71 frame should not produce ImuSample", result.isEmpty())

        assertNotNull("onRegisterRead callback should have been invoked", callbackResult)
        callbackResult!!.let { rr ->
            assertEquals("Register should be 0x64", 0x64, rr.register)
            assertEquals("Data should have 8 shorts", 8, rr.data.size)
            assertEquals("Battery value should be 780", 780, rr.data[0].toInt())
            assertEquals(0, rr.data[1].toInt())
            assertEquals(0, rr.data[7].toInt())
        }
    }

    @Test
    fun parseRegisterReadResponseDoesNotInterfereWithImuCycle() {
        var callbackResult: RegisterReadResult? = null
        parser.onRegisterRead = { callbackResult = it }

        val t0 = 1_000_000_000L

        val accData = ByteArray(8)
        writeInt16LE(accData, 0, 2048)
        val accFrame = buildFrame(0x51, accData)
        parser.feed(accFrame, t0)

        val dataValues = ShortArray(8)
        dataValues[0] = 1000
        val regFrame = buildRegReadFrame(0x50, dataValues)
        parser.feed(regFrame, t0 + 1_000_000L)

        assertNotNull("onRegisterRead should fire for 0x71", callbackResult)
        assertEquals(0x50, callbackResult!!.register)

        val gyroData = ByteArray(8)
        writeInt16LE(gyroData, 0, 1000)
        val gyroFrame = buildFrame(0x52, gyroData)

        val quatData = ByteArray(8)
        writeInt16LE(quatData, 0, 16384)
        val quatFrame = buildFrame(0x59, quatData)

        val combined = gyroFrame + quatFrame
        val result = parser.feed(combined, t0 + 5_000_000L)
        assertTrue("IMU cycle should complete after 0x71 interjection", result.isNotEmpty())
        assertEquals(0, parser.droppedPartialCount)
    }

    @Test
    fun parseRegisterReadResponseNoChecksum() {
        // Verify that byte 10 (data[3] low) does NOT cause checksum failure
        var callbackResult: RegisterReadResult? = null
        parser.onRegisterRead = { callbackResult = it }

        val dataValues = ShortArray(8)
        dataValues[0] = 780
        dataValues[3] = 0x55AA.toShort() // non-zero value at data[3], bytes 10-11
        val frame = buildRegReadFrame(0x64, dataValues)

        val result = parser.feed(frame, 1_000_000_000L)

        assertTrue("0x71 should not produce ImuSample", result.isEmpty())
        assertNotNull("0x71 callback should fire regardless of byte 10 value", callbackResult)
        assertEquals(0x64, callbackResult!!.register)
        assertEquals(0x55AA, callbackResult.data[3].toInt() and 0xFFFF)
    }

    @Test
    fun parseRegisterReadInterleavedWithCombined() {
        // 0x71 frame between two 0x61 frames in a single buffer
        var regCallback: RegisterReadResult? = null
        parser.onRegisterRead = { regCallback = it }

        val t0 = 1_000_000_000L

        fun buildCombinedFrame(
            accX: Short,
            gyroX: Short,
            roll: Short,
        ): ByteArray {
            val frame = ByteArray(20)
            frame[0] = 0x55.toByte()
            frame[1] = 0x61.toByte()
            writeInt16LE(frame, 2, accX)
            writeInt16LE(frame, 4, 0)
            writeInt16LE(frame, 6, 0)
            writeInt16LE(frame, 8, gyroX)
            writeInt16LE(frame, 10, 0)
            writeInt16LE(frame, 12, 0)
            writeInt16LE(frame, 14, roll)
            writeInt16LE(frame, 16, 0)
            writeInt16LE(frame, 18, 0)
            return frame
        }

        val imuFrame1 = buildCombinedFrame(2048, 1000, 0)
        val dataValues = ShortArray(8)
        dataValues[0] = 780
        val regFrame = buildRegReadFrame(0x64, dataValues)
        val imuFrame2 = buildCombinedFrame(4096, 2000, 90)

        val combined = imuFrame1 + regFrame + imuFrame2
        val result = parser.feed(combined, t0)

        assertEquals("Two IMU samples from combined frames", 2, result.size)
        assertNotNull("Register read callback should fire", regCallback)
        assertEquals(0x64, regCallback!!.register)
    }

    // --- Test 9: Multiple combined frames in one BLE notification ---

    @Test
    fun multipleCombinedFramesInOneNotification() {
        val t0 = 1_000_000_000L

        // Build two 0x61 combined frames concatenated
        // 0x61 frame: [0x55][0x61][AccX][AccY][AccZ][GyrX][GyrY][GyrZ][Roll][Pitch][Yaw]
        fun buildCombinedFrame(
            accX: Short,
            gyroX: Short,
            roll: Short,
        ): ByteArray {
            val frame = ByteArray(20)
            frame[0] = 0x55.toByte()
            frame[1] = 0x61.toByte()
            writeInt16LE(frame, 2, accX)
            writeInt16LE(frame, 4, 0) // accY
            writeInt16LE(frame, 6, 0) // accZ
            writeInt16LE(frame, 8, gyroX)
            writeInt16LE(frame, 10, 0) // gyroY
            writeInt16LE(frame, 12, 0) // gyroZ
            writeInt16LE(frame, 14, roll)
            writeInt16LE(frame, 16, 0) // pitch
            writeInt16LE(frame, 18, 0) // yaw
            return frame
        }

        val frame1 = buildCombinedFrame(2048, 1000, 0) // accX≈1g, gyroX≈61°/s
        val frame2 = buildCombinedFrame(4096, 2000, 90) // accX≈2g, gyroX≈122°/s

        val combined = frame1 + frame2
        val result = parser.feed(combined, t0)

        assertEquals("Two combined frames should produce 2 samples", 2, result.size)
    }
}
