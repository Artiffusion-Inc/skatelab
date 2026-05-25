package ru.skatelab.capture.data.export

import java.io.File
import java.io.FileInputStream
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.proto.Imu.IMURecord

class ImuStreamWriterTest {
    @Test
    fun `write 2 samples and read back with parseDelimitedFrom`() {
        val tempFile = File.createTempFile("imu_stream", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)

        val sample1 =
            ImuSample(
                timestampNs = 10_000_000_000L,
                accX = 0.1f, accY = 0.2f, accZ = 9.81f,
                gyroX = 0.01f, gyroY = 0.02f, gyroZ = 0.03f,
                quatW = 1.0f, quatX = 0.0f, quatY = 0.0f, quatZ = 0.0f,
            )
        val sample2 =
            ImuSample(
                timestampNs = 10_010_000_000L,
                accX = 0.3f, accY = 0.4f, accZ = 9.80f,
                gyroX = 0.04f, gyroY = 0.05f, gyroZ = 0.06f,
                quatW = 0.99f, quatX = 0.01f, quatY = 0.02f, quatZ = 0.03f,
            )

        writer.write(sample1)
        writer.write(sample2)
        writer.close()

        // Read back using parseDelimitedFrom
        val fis = FileInputStream(tempFile)
        val record1 = IMURecord.parseDelimitedFrom(fis)
        val record2 = IMURecord.parseDelimitedFrom(fis)
        fis.close()

        assertTrue("First record should have sample", record1.hasSample())
        assertTrue("Second record should have sample", record2.hasSample())

        val proto1 = record1.sample
        assertEquals(10_000_000_000L, proto1.timestampNs)
        assertEquals(0.1f, proto1.accX, 0.001f)
        assertEquals(0.2f, proto1.accY, 0.001f)
        assertEquals(9.81f, proto1.accZ, 0.001f)
        assertEquals(0.01f, proto1.gyroX, 0.001f)
        assertEquals(0.02f, proto1.gyroY, 0.001f)
        assertEquals(0.03f, proto1.gyroZ, 0.001f)
        assertEquals(1.0f, proto1.quatW, 0.001f)
        assertEquals(0.0f, proto1.quatX, 0.001f)
        assertEquals(0.0f, proto1.quatY, 0.001f)
        assertEquals(0.0f, proto1.quatZ, 0.001f)

        val proto2 = record2.sample
        assertEquals(10_010_000_000L, proto2.timestampNs)
        assertEquals(0.3f, proto2.accX, 0.001f)
        assertEquals(0.99f, proto2.quatW, 0.001f)
        assertEquals(0.03f, proto2.quatZ, 0.001f)
    }

    @Test
    fun `empty file produces no records`() {
        val tempFile = File.createTempFile("imu_empty", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)
        writer.close()

        val bytes = tempFile.readBytes()
        assertEquals(0, bytes.size)
    }

    @Test
    fun `write many samples and verify count`() {
        val tempFile = File.createTempFile("imu_many", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)

        val sample =
            ImuSample(
                timestampNs = 0L,
                accX = 0f, accY = 0f, accZ = 9.81f,
                gyroX = 0f, gyroY = 0f, gyroZ = 0f,
                quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
            )

        repeat(100) { i ->
            writer.write(sample.copy(timestampNs = i * 10_000_000L))
        }
        writer.close()

        val fis = FileInputStream(tempFile)
        var count = 0
        while (true) {
            val record = IMURecord.parseDelimitedFrom(fis) ?: break
            if (!record.hasSample()) break
            count++
        }
        fis.close()
        assertEquals(100, count)
    }

    @Test
    fun `writeGap writes IMUGap record`() {
        val tempFile = File.createTempFile("imu_gap", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)

        writer.writeGap(lastSampleNs = 1_000_000_000L, firstSampleNs = 1_500_000_000L, reconnectSeq = 1)
        writer.close()

        val fis = FileInputStream(tempFile)
        val record = IMURecord.parseDelimitedFrom(fis)
        fis.close()

        assertTrue("Record should have gap", record!!.hasGap())
        assertEquals(1_000_000_000L, record.gap.lastSampleNs)
        assertEquals(1_500_000_000L, record.gap.firstSampleNs)
        assertEquals(1, record.gap.reconnectSeq)
    }

    @Test
    fun `writeGap followed by sample preserves both`() {
        val tempFile = File.createTempFile("imu_gap_sample", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)

        writer.writeGap(lastSampleNs = 900_000_000L, firstSampleNs = 950_000_000L, reconnectSeq = 2)
        writer.write(
            ImuSample(
                timestampNs = 1_000_000_000L,
                accX = 0f, accY = 0f, accZ = 9.8f,
                gyroX = 0f, gyroY = 0f, gyroZ = 0f,
                quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
            ),
        )
        writer.close()

        val fis = FileInputStream(tempFile)
        val record1 = IMURecord.parseDelimitedFrom(fis)
        val record2 = IMURecord.parseDelimitedFrom(fis)
        fis.close()

        assertTrue("First record should be gap", record1!!.hasGap())
        assertTrue("Second record should be sample", record2!!.hasSample())
        assertEquals(2, record1.gap.reconnectSeq)
        assertEquals(1_000_000_000L, record2.sample.timestampNs)
    }

    @Test(expected = IllegalStateException::class)
    fun `write without open throws`() {
        val writer = ImuStreamWriter()
        writer.write(
            ImuSample(
                timestampNs = 0L,
                accX = 0f, accY = 0f, accZ = 0f,
                gyroX = 0f, gyroY = 0f, gyroZ = 0f,
                quatW = 1f, quatX = 0f, quatY = 0f, quatZ = 0f,
            ),
        )
    }

    @Test(expected = IllegalStateException::class)
    fun `writeGap without open throws`() {
        val writer = ImuStreamWriter()
        writer.writeGap(0L, 0L, 0)
    }

    @Test
    fun `flush without open is no-op`() {
        val writer = ImuStreamWriter()
        writer.flush() // should not throw
    }

    @Test
    fun `close without open is no-op`() {
        val writer = ImuStreamWriter()
        writer.close() // should not throw
    }
}
