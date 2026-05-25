package ru.skatelab.capture.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Test

class ImuChartDataTest {
    private fun makeData(
        timeSeconds: FloatArray = floatArrayOf(0f),
        accMagLeft: FloatArray = floatArrayOf(9.8f),
        angVelLeft: FloatArray = floatArrayOf(0f),
        rotLeft: FloatArray = floatArrayOf(0f),
        accMagRight: FloatArray = floatArrayOf(9.8f),
        angVelRight: FloatArray = floatArrayOf(0f),
        rotRight: FloatArray = floatArrayOf(0f),
    ) = ImuChartData(timeSeconds, accMagLeft, angVelLeft, rotLeft, accMagRight, angVelRight, rotRight)

    @Test
    fun equals_sameValues_returnsTrue() {
        val a = makeData(timeSeconds = floatArrayOf(0f, 1f), accMagLeft = floatArrayOf(9.8f, 9.8f))
        val b = makeData(timeSeconds = floatArrayOf(0f, 1f), accMagLeft = floatArrayOf(9.8f, 9.8f))
        assertEquals(a, b)
    }

    @Test
    fun equals_differentTimeSeconds_returnsFalse() {
        val a = makeData(timeSeconds = floatArrayOf(0f, 1f))
        val b = makeData(timeSeconds = floatArrayOf(0f, 2f))
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentAccMagLeft_returnsFalse() {
        val a = makeData(accMagLeft = floatArrayOf(9.8f))
        val b = makeData(accMagLeft = floatArrayOf(5.0f))
        assertNotEquals(a, b)
    }

    @Test
    fun equals_sameReference_returnsTrue() {
        val a = makeData()
        assertEquals(a, a)
    }

    @Test
    fun equals_differentType_returnsFalse() {
        val a = makeData()
        assertFalse(a.equals("not ImuChartData"))
    }

    @Test
    fun hashCode_sameValues_returnsSameHashCode() {
        val a = makeData()
        val b = makeData()
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun emptyArrays_validConstruction() {
        val data =
            ImuChartData(
                timeSeconds = floatArrayOf(),
                accMagLeft = floatArrayOf(),
                angVelLeft = floatArrayOf(),
                rotLeft = floatArrayOf(),
                accMagRight = floatArrayOf(),
                angVelRight = floatArrayOf(),
                rotRight = floatArrayOf(),
            )
        assertEquals(0, data.timeSeconds.size)
    }
}
