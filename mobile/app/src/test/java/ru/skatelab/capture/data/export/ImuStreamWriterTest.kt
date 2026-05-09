package ru.skatelab.capture.data.export

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.proto.Imu.IMURecord
import java.io.File
import java.io.FileInputStream

class ImuStreamWriterTest {

    @Test
    fun `write 2 samples and read back with parseDelimitedFrom`() {
        val tempFile = File.createTempFile("imu_stream", ".binpb")
        tempFile.deleteOnExit()

        val writer = ImuStreamWriter()
        writer.open(tempFile)

        val sample1 = ImuSample(
            timestampNs = 10_000_000_000L,
            accX = 0.1f, accY = 0.2f, accZ = 9.81f,
            gyroX = 0.01f, gyroY = 0.02f, gyroZ = 0.03f,
            quatW = 1.0f, quatX = 0.0f, quatY = 0.0f, quatZ = 0.0f,
        )
        val sample2 = ImuSample(
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
}
