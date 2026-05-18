package ru.skatelab.capture.data.imu

import java.io.File
import java.io.FileInputStream
import kotlin.math.sqrt
import ru.skatelab.capture.domain.model.ImuChartData
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.proto.Imu.IMURecord

object ImuParser {
    fun parse(leftFile: File, rightFile: File): ImuChartData {
        val leftSamples = parseFile(leftFile)
        val rightSamples = parseFile(rightFile)

        val t0Ns = minOf(
            leftSamples.firstOrNull()?.timestampNs ?: Long.MAX_VALUE,
            rightSamples.firstOrNull()?.timestampNs ?: Long.MAX_VALUE,
        )
        if (t0Ns == Long.MAX_VALUE) {
            return ImuChartData(
                timeSeconds = FloatArray(0),
                accMagLeft = FloatArray(0),
                angVelLeft = FloatArray(0),
                accMagRight = FloatArray(0),
                angVelRight = FloatArray(0),
            )
        }

        val maxSize = maxOf(leftSamples.size, rightSamples.size)
        val timeSeconds = FloatArray(maxSize)
        val accMagLeft = FloatArray(maxSize)
        val angVelLeft = FloatArray(maxSize)
        val accMagRight = FloatArray(maxSize)
        val angVelRight = FloatArray(maxSize)

        for (i in 0 until maxSize) {
            val leftTs = leftSamples.getOrNull(i)?.timestampNs
            val rightTs = rightSamples.getOrNull(i)?.timestampNs
            val ts = leftTs ?: rightTs ?: t0Ns
            timeSeconds[i] = (ts - t0Ns) / 1_000_000_000f

            leftSamples.getOrNull(i)?.let { s ->
                accMagLeft[i] = magnitude(s.accX, s.accY, s.accZ)
                angVelLeft[i] = magnitude(s.gyroX, s.gyroY, s.gyroZ)
            }
            rightSamples.getOrNull(i)?.let { s ->
                accMagRight[i] = magnitude(s.accX, s.accY, s.accZ)
                angVelRight[i] = magnitude(s.gyroX, s.gyroY, s.gyroZ)
            }
        }

        return ImuChartData(
            timeSeconds = timeSeconds,
            accMagLeft = accMagLeft,
            angVelLeft = angVelLeft,
            accMagRight = accMagRight,
            angVelRight = angVelRight,
        )
    }

    fun parseFile(file: File): List<ImuSample> {
        if (!file.exists() || file.length() == 0L) return emptyList()

        val samples = mutableListOf<ImuSample>()
        FileInputStream(file).use { fis ->
            while (fis.available() > 0) {
                val record = IMURecord.parseDelimitedFrom(fis) ?: break
                if (record.hasSample()) {
                    val s = record.sample
                    samples.add(
                        ImuSample(
                            timestampNs = s.timestampNs,
                            accX = s.accX,
                            accY = s.accY,
                            accZ = s.accZ,
                            gyroX = s.gyroX,
                            gyroY = s.gyroY,
                            gyroZ = s.gyroZ,
                            quatW = s.quatW,
                            quatX = s.quatX,
                            quatY = s.quatY,
                            quatZ = s.quatZ,
                        ),
                    )
                }
                // IMUGap records are skipped — only IMUSample records are extracted
            }
        }
        return samples
    }

    private fun magnitude(x: Float, y: Float, z: Float): Float =
        sqrt(x * x + y * y + z * z)
}