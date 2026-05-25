package ru.skatelab.capture.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class ImuSampleTest {
    private fun makeSample(
        timestampNs: Long = 1_000L,
        accX: Float = 0f,
        accY: Float = 0f,
        accZ: Float = 9.8f,
        gyroX: Float = 0f,
        gyroY: Float = 0f,
        gyroZ: Float = 0f,
        quatW: Float = 1f,
        quatX: Float = 0f,
        quatY: Float = 0f,
        quatZ: Float = 0f,
    ) = ImuSample(timestampNs, accX, accY, accZ, gyroX, gyroY, gyroZ, quatW, quatX, quatY, quatZ)

    @Test
    fun equals_sameValues_returnsTrue() {
        val a = makeSample(timestampNs = 1_000_000_000L, accX = 0.1f, accY = 0.2f, accZ = 9.8f)
        val b = makeSample(timestampNs = 1_000_000_000L, accX = 0.1f, accY = 0.2f, accZ = 9.8f)
        assertEquals(a, b)
    }

    @Test
    fun equals_differentTimestamp_returnsFalse() {
        val a = makeSample(timestampNs = 1_000L)
        val b = makeSample(timestampNs = 2_000L)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentAcc_returnsFalse() {
        val a = makeSample(accX = 1f)
        val b = makeSample(accX = 2f)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentQuat_returnsFalse() {
        val a = makeSample(quatW = 1f, quatX = 0f)
        val b = makeSample(quatW = 0f, quatX = 1f)
        assertNotEquals(a, b)
    }

    @Test
    fun hashCode_sameValues_returnsSameHashCode() {
        val a = makeSample()
        val b = makeSample()
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun copy_modifiesField() {
        val a = makeSample(accZ = 9.8f)
        val b = a.copy(accZ = 10.0f)
        assertEquals(10.0f, b.accZ, 0.001f)
        assertEquals(9.8f, a.accZ, 0.001f)
    }
}
