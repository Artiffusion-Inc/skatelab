package ru.skatelab.capture.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CalibrationDataTest {
    @Test
    fun identity_hasUnitQuaternionAndZeroTimestamp() {
        val identity = CalibrationData.IDENTITY
        assertEquals(floatArrayOf(1f, 0f, 0f, 0f).toList(), identity.quatRef.toList())
        assertEquals(0L, identity.calibratedAt)
    }

    @Test
    fun constructor_requiresFourComponents() {
        try {
            CalibrationData(floatArrayOf(1f, 0f), 0L)
            assert(false) { "Should have thrown IllegalArgumentException" }
        } catch (e: IllegalArgumentException) {
            assertTrue(e.message!!.contains("4"))
        }
    }

    @Test
    fun equals_sameValues_returnsTrue() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        assertEquals(a, b)
    }

    @Test
    fun equals_differentQuaternion_returnsFalse() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 1000L)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentTimestamp_returnsFalse() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 2000L)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentType_returnsFalse() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        assertFalse(a.equals("not a CalibrationData"))
    }

    @Test
    fun equals_sameReference_returnsTrue() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        assertEquals(a, a)
    }

    @Test
    fun hashCode_sameValues_returnsSameHashCode() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun hashCode_differentValues_returnsDifferentHashCode() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = CalibrationData(floatArrayOf(0f, 1f, 0f, 0f), 2000L)
        // Not guaranteed but highly likely
        assertTrue(a.hashCode() != b.hashCode())
    }

    @Test
    fun copy_producesEqualObject() {
        val a = CalibrationData(floatArrayOf(0.7071f, 0.7071f, 0f, 0f), 5000L)
        val b = a.copy()
        assertEquals(a, b)
    }

    @Test
    fun copy_withModification_changesField() {
        val a = CalibrationData(floatArrayOf(1f, 0f, 0f, 0f), 1000L)
        val b = a.copy(calibratedAt = 2000L)
        assertEquals(2000L, b.calibratedAt)
        assertNotEquals(a, b)
    }
}
