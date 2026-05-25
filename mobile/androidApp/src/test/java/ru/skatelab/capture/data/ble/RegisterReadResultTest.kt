package ru.skatelab.capture.data.ble

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RegisterReadResultTest {
    @Test
    fun equals_sameValues_returnsTrue() {
        val a = RegisterReadResult(0x64, shortArrayOf(780, 0, 0, 0, 0, 0, 0, 0))
        val b = RegisterReadResult(0x64, shortArrayOf(780, 0, 0, 0, 0, 0, 0, 0))
        assertEquals(a, b)
    }

    @Test
    fun equals_differentRegister_returnsFalse() {
        val a = RegisterReadResult(0x64, shortArrayOf(0, 0, 0, 0, 0, 0, 0, 0))
        val b = RegisterReadResult(0x50, shortArrayOf(0, 0, 0, 0, 0, 0, 0, 0))
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentData_returnsFalse() {
        val a = RegisterReadResult(0x64, shortArrayOf(100, 0, 0, 0, 0, 0, 0, 0))
        val b = RegisterReadResult(0x64, shortArrayOf(200, 0, 0, 0, 0, 0, 0, 0))
        assertNotEquals(a, b)
    }

    @Test
    fun equals_sameReference_returnsTrue() {
        val a = RegisterReadResult(0x64, shortArrayOf())
        assertEquals(a, a)
    }

    @Test
    fun equals_differentType_returnsFalse() {
        val a = RegisterReadResult(0x64, shortArrayOf())
        assertFalse(a.equals("not RegisterReadResult"))
    }

    @Test
    fun hashCode_sameValues_returnsSameHashCode() {
        val a = RegisterReadResult(0x64, shortArrayOf(780, 0))
        val b = RegisterReadResult(0x64, shortArrayOf(780, 0))
        assertEquals(a.hashCode(), b.hashCode())
    }

    @Test
    fun hashCode_differentValues_returnsDifferentHashCode() {
        val a = RegisterReadResult(0x64, shortArrayOf(780))
        val b = RegisterReadResult(0x50, shortArrayOf(100))
        assertTrue(a.hashCode() != b.hashCode())
    }

    @Test
    fun data_shortArray_contentComparison() {
        val a = RegisterReadResult(0x64, shortArrayOf(1, 2, 3, 4, 5, 6, 7, 8))
        val b = RegisterReadResult(0x64, shortArrayOf(1, 2, 3, 4, 5, 6, 7, 8))
        assertEquals(a, b) // contentEquals works for ShortArray
    }
}
