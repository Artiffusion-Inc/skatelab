package ru.skatelab.capture.data.imu

import java.io.File
import java.io.FileOutputStream
import kotlin.math.sqrt
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import ru.skatelab.capture.proto.Imu.IMUGap
import ru.skatelab.capture.proto.Imu.IMURecord
import ru.skatelab.capture.proto.Imu.IMUSample

class ImuParserTest {
    @get:Rule
    val tempFolder = TemporaryFolder()

    private lateinit var leftFile: File
    private lateinit var rightFile: File

    @Before
    fun setUp() {
        leftFile = tempFolder.newFile("left.binpb")
        rightFile = tempFolder.newFile("right.binpb")
    }

    // --- Magnitude tests ---

    @Test
    fun accMagnitude_sqrtOfSumOfSquares() {
        val sample =
            buildSample(
                timestampNs = 1_000_000_000L,
                accX = 3f,
                accY = 4f,
                accZ = 0f,
            )
        writeRecords(leftFile, listOf(sample))
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L)))

        val data = ImuParser.parse(leftFile, rightFile)
        val expected = sqrt(3f * 3f + 4f * 4f + 0f * 0f)
        assertEquals(expected, data.accMagLeft[0], 0.001f)
    }

    @Test
    fun angVelMagnitude_sqrtOfSumOfSquares() {
        val sample =
            buildSample(
                timestampNs = 1_000_000_000L,
                gyroX = 1f,
                gyroY = 2f,
                gyroZ = 2f,
            )
        writeRecords(leftFile, listOf(sample))
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L)))

        val data = ImuParser.parse(leftFile, rightFile)
        val expected = sqrt(1f * 1f + 2f * 2f + 2f * 2f)
        assertEquals(expected, data.angVelLeft[0], 0.001f)
    }

    @Test
    fun accMagnitude_threeAxisNonTrivial() {
        val sample =
            buildSample(
                timestampNs = 1_000_000_000L,
                accX = 1f,
                accY = 2f,
                accZ = 3f,
            )
        writeRecords(leftFile, listOf(sample))
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L)))

        val data = ImuParser.parse(leftFile, rightFile)
        val expected = sqrt(1f + 4f + 9f)
        assertEquals(expected, data.accMagLeft[0], 0.001f)
    }

    // --- Session-relative time tests ---

    @Test
    fun firstSampleAtTimeZero() {
        val t0 = 5_000_000_000L
        writeRecords(leftFile, listOf(buildSample(timestampNs = t0)))
        writeRecords(rightFile, listOf(buildSample(timestampNs = t0)))

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0f, data.timeSeconds[0], 0.001f)
    }

    @Test
    fun secondSampleAtOneSecond() {
        val t0 = 5_000_000_000L
        val t1 = 6_000_000_000L
        writeRecords(
            leftFile,
            listOf(
                buildSample(timestampNs = t0),
                buildSample(timestampNs = t1),
            ),
        )
        writeRecords(
            rightFile,
            listOf(
                buildSample(timestampNs = t0),
                buildSample(timestampNs = t1),
            ),
        )

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0f, data.timeSeconds[0], 0.001f)
        assertEquals(1f, data.timeSeconds[1], 0.001f)
    }

    @Test
    fun timeRelativeToEarliestSensor() {
        val leftT0 = 10_000_000_000L
        val rightT0 = 10_500_000_000L // 0.5s later
        writeRecords(leftFile, listOf(buildSample(timestampNs = leftT0)))
        writeRecords(rightFile, listOf(buildSample(timestampNs = rightT0)))

        val data = ImuParser.parse(leftFile, rightFile)
        // t0 is leftT0 (earliest)
        assertEquals(0f, data.timeSeconds[0], 0.001f)
    }

    // --- Empty file tests ---

    @Test
    fun bothFilesEmpty_returnEmptyData() {
        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0, data.timeSeconds.size)
        assertEquals(0, data.accMagLeft.size)
        assertEquals(0, data.angVelLeft.size)
        assertEquals(0, data.accMagRight.size)
        assertEquals(0, data.angVelRight.size)
    }

    @Test
    fun oneFileEmpty_otherHasData() {
        val t0 = 1_000_000_000L
        writeRecords(leftFile, listOf(buildSample(timestampNs = t0, accX = 3f, accY = 4f)))
        // rightFile is empty

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(1, data.timeSeconds.size)
        assertEquals(0f, data.accMagRight[0], 0.001f) // default 0 for missing sensor
        assertEquals(5f, data.accMagLeft[0], 0.001f) // sqrt(9+16)
    }

    @Test
    fun nonexistentFile_treatedAsEmpty() {
        val missingFile = File(tempFolder.root, "nonexistent.binpb")
        val t0 = 1_000_000_000L
        writeRecords(leftFile, listOf(buildSample(timestampNs = t0)))

        val data = ImuParser.parse(leftFile, missingFile)
        assertEquals(1, data.timeSeconds.size)
    }

    // --- Proto3 default values test ---

    @Test
    fun proto3DefaultValues_missingFieldsAreZero() {
        // Build a sample with only timestamp set — all float fields default to 0.0 in proto3
        val protoSample =
            IMUSample.newBuilder()
                .setTimestampNs(1_000_000_000L)
                .build() // acc/gyro/quat all 0.0 by default
        val record = IMURecord.newBuilder().setSample(protoSample).build()

        writeRecords(leftFile, listOf(record))
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L)))

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0f, data.accMagLeft[0], 0.001f) // magnitude of (0,0,0) = 0
        assertEquals(0f, data.angVelLeft[0], 0.001f)
    }

    // --- IMUGap skipping test ---

    @Test
    fun gapRecordsSkipped_onlySamplesExtracted() {
        val sampleRecord = buildSample(timestampNs = 1_000_000_000L, accX = 3f, accY = 4f)
        val gap =
            IMUGap.newBuilder()
                .setLastSampleNs(900_000_000L)
                .setFirstSampleNs(950_000_000L)
                .setReconnectSeq(1)
                .build()
        val gapRecord = IMURecord.newBuilder().setGap(gap).build()

        FileOutputStream(leftFile).use { fos ->
            gapRecord.writeDelimitedTo(fos) // gap first
            sampleRecord.writeDelimitedTo(fos) // sample second
        }
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L)))

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(1, data.accMagLeft.size) // only the sample, gap skipped
        assertEquals(5f, data.accMagLeft[0], 0.001f) // sqrt(9+16)
    }

    // --- parseFile standalone test ---

    @Test
    fun parseFile_returnsCorrectSamples() {
        val samples =
            listOf(
                buildSample(timestampNs = 1_000_000_000L, accX = 1f, gyroX = 10f),
                buildSample(timestampNs = 2_000_000_000L, accX = 2f, gyroX = 20f),
            )
        writeRecords(leftFile, samples)

        val result = ImuParser.parseFile(leftFile)
        assertEquals(2, result.size)
        assertEquals(1_000_000_000L, result[0].timestampNs)
        assertEquals(1f, result[0].accX, 0.001f)
        assertEquals(10f, result[0].gyroX, 0.001f)
        assertEquals(2_000_000_000L, result[1].timestampNs)
        assertEquals(2f, result[1].accX, 0.001f)
    }

    // --- Asymmetric length test ---

    @Test
    fun differentLengthFiles_paddedWithZeros() {
        writeRecords(
            leftFile,
            listOf(
                buildSample(timestampNs = 1_000_000_000L, accX = 1f),
                buildSample(timestampNs = 2_000_000_000L, accX = 2f),
            ),
        )
        writeRecords(
            rightFile,
            listOf(
                buildSample(timestampNs = 1_000_000_000L, accX = 10f),
            ),
        )

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(2, data.timeSeconds.size)
        assertEquals(0f, data.accMagRight[1], 0.001f) // no second right sample → 0
    }

    // --- Accumulated rotation tests ---

    @Test
    fun rotation_firstSampleIsZero() {
        writeRecords(leftFile, listOf(buildSample(timestampNs = 1_000_000_000L, quatW = 1f)))
        writeRecords(rightFile, listOf(buildSample(timestampNs = 1_000_000_000L, quatW = 1f)))

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0f, data.rotLeft[0], 0.001f)
    }

    @Test
    fun rotation_identicalQuaternion_noAccumulation() {
        // Same quaternion on every sample → dot=1 → angle=0 → accumulated stays 0
        writeRecords(
            leftFile,
            listOf(
                buildSample(timestampNs = 1_000_000_000L, quatW = 1f),
                buildSample(timestampNs = 2_000_000_000L, quatW = 1f),
                buildSample(timestampNs = 3_000_000_000L, quatW = 1f),
            ),
        )
        writeRecords(
            rightFile,
            listOf(buildSample(timestampNs = 1_000_000_000L, quatW = 1f)),
        )

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0f, data.rotLeft[0], 0.001f)
        assertEquals(0f, data.rotLeft[1], 0.001f)
        assertEquals(0f, data.rotLeft[2], 0.001f)
    }

    @Test
    fun rotation_90degreeYawStep_accumulatesCorrectly() {
        // Sample 1: identity quaternion (w=1, x=0, y=0, z=0)
        // Sample 2: 90° yaw = (w=cos45, x=0, y=0, z=sin45)
        val cos45 = kotlin.math.cos(Math.toRadians(45.0)).toFloat()
        val sin45 = kotlin.math.sin(Math.toRadians(45.0)).toFloat()
        writeRecords(
            leftFile,
            listOf(
                buildSample(timestampNs = 1_000_000_000L, quatW = 1f),
                buildSample(timestampNs = 2_000_000_000L, quatW = cos45, quatZ = sin45),
            ),
        )
        writeRecords(
            rightFile,
            listOf(buildSample(timestampNs = 1_000_000_000L, quatW = 1f)),
        )

        val data = ImuParser.parse(leftFile, rightFile)
        // dot = 1*cos45 + 0 + 0 + 0*sin45 = cos45 ≈ 0.707
        // stepAngle = 2 * acos(|cos45|) = 2 * acos(0.707) ≈ 2 * 0.785 = 1.57 rad ≈ 90°
        assertEquals(0f, data.rotLeft[0], 0.001f) // first sample is 0
        assertEquals(1.57f, data.rotLeft[1], 0.05f) // ~90° in radians
    }

    // --- roundTo4 precision test ---

    @Test
    fun timeSeconds_roundedTo4DecimalPlaces() {
        // 333ms offset → 0.333333... should be rounded to 0.3333
        val t0 = 1_000_000_000L
        val t1 = 1_333_000_000L // 333ms later
        writeRecords(
            leftFile,
            listOf(
                buildSample(timestampNs = t0),
                buildSample(timestampNs = t1),
            ),
        )
        writeRecords(
            rightFile,
            listOf(buildSample(timestampNs = t0)),
        )

        val data = ImuParser.parse(leftFile, rightFile)
        assertEquals(0.3333f, data.timeSeconds[1], 0.0001f)
    }

    // --- Helpers ---

    private fun buildSample(
        timestampNs: Long,
        accX: Float = 0f,
        accY: Float = 0f,
        accZ: Float = 0f,
        gyroX: Float = 0f,
        gyroY: Float = 0f,
        gyroZ: Float = 0f,
        quatW: Float = 1f,
        quatX: Float = 0f,
        quatY: Float = 0f,
        quatZ: Float = 0f,
    ): IMURecord {
        val sample =
            IMUSample.newBuilder()
                .setTimestampNs(timestampNs)
                .setAccX(accX)
                .setAccY(accY)
                .setAccZ(accZ)
                .setGyroX(gyroX)
                .setGyroY(gyroY)
                .setGyroZ(gyroZ)
                .setQuatW(quatW)
                .setQuatX(quatX)
                .setQuatY(quatY)
                .setQuatZ(quatZ)
                .build()
        return IMURecord.newBuilder().setSample(sample).build()
    }

    private fun writeRecords(
        file: File,
        records: List<IMURecord>,
    ) {
        FileOutputStream(file).use { fos ->
            for (record in records) {
                record.writeDelimitedTo(fos)
            }
        }
    }
}
