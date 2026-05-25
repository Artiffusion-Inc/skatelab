package ru.skatelab.capture.data.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CommandStepTest {
    @Test
    fun equals_sameBytesAndDelay_returnsTrue() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x69, 0x88.toByte(), 0xB5.toByte()), 50L)
        val b = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x69, 0x88.toByte(), 0xB5.toByte()), 50L)
        assertEquals(a, b)
    }

    @Test
    fun equals_differentBytes_returnsFalse() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte(), 0xAA.toByte()), 50L)
        val b = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte(), 0xAB.toByte()), 50L)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentDelay_returnsFalse() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte()), 50L)
        val b = Wt901Commander.CommandStep(byteArrayOf(0xFF.toByte()), 100L)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_sameReference_returnsTrue() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0x01), 10L)
        assertEquals(a, a)
    }

    @Test
    fun hashCode_sameBytesAndDelay_returnsSameHashCode() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0x01, 0x02), 30L)
        val b = Wt901Commander.CommandStep(byteArrayOf(0x01, 0x02), 30L)
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun hashCode_differentValues_returnsDifferentHashCode() {
        val a = Wt901Commander.CommandStep(byteArrayOf(0x01), 10L)
        val b = Wt901Commander.CommandStep(byteArrayOf(0x02), 10L)
        assertTrue(a.hashCode() != b.hashCode())
    }
}
