package ru.skatelab.capture.data.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class Wt901CommanderTest {

    // --- Individual command byte format tests ---

    @Test
    fun unlockCommand() {
        val bytes = Wt901Commander.unlock()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x69, 0x88.toByte(), 0xB5.toByte()),
            bytes,
        )
    }

    @Test
    fun setOutputContentCommand() {
        val bytes = Wt901Commander.setOutputContent(0x0046)
        // 0x0046 → low byte = 0x46, high byte = 0x00
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x02, 0x46, 0x00),
            bytes,
        )
    }

    @Test
    fun setOutputContentDisableCommand() {
        val bytes = Wt901Commander.setOutputContent(0x0000)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x02, 0x00, 0x00),
            bytes,
        )
    }

    @Test
    fun setOutputRateCommand() {
        val bytes = Wt901Commander.setOutputRate(0x09)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x03, 0x09, 0x00),
            bytes,
        )
    }

    @Test
    fun saveCommand() {
        val bytes = Wt901Commander.save()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x00, 0x00, 0x00),
            bytes,
        )
    }

    @Test
    fun readRegisterCommand() {
        val bytes = Wt901Commander.readRegister(0x0A)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x27, 0x0A, 0x00),
            bytes,
        )
    }

    @Test
    fun readRegisterTimeCommand() {
        val bytes = Wt901Commander.readRegister(0x30)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x27, 0x30, 0x00),
            bytes,
        )
    }

    // --- Sequence tests ---

    @Test
    fun configureSequenceLength() {
        val seq = Wt901Commander.configureSequence()
        assertEquals("Configure sequence should have 4 steps", 4, seq.size)
    }

    @Test
    fun configureSequenceDelays() {
        val seq = Wt901Commander.configureSequence()
        assertEquals(50L, seq[0].delayAfterMs)  // Unlock → 50ms
        assertEquals(100L, seq[1].delayAfterMs) // OutputContent → 100ms
        assertEquals(100L, seq[2].delayAfterMs) // OutputRate → 100ms
        assertEquals(500L, seq[3].delayAfterMs) // Save → 500ms
    }

    @Test
    fun configureSequenceCommandBytes() {
        val seq = Wt901Commander.configureSequence()
        assertArrayEquals(Wt901Commander.unlock(), seq[0].bytes)
        assertArrayEquals(Wt901Commander.setOutputContent(0x0046), seq[1].bytes)
        assertArrayEquals(Wt901Commander.setOutputRate(0x09), seq[2].bytes)
        assertArrayEquals(Wt901Commander.save(), seq[3].bytes)
    }

    @Test
    fun startStreamingSequenceLength() {
        val seq = Wt901Commander.startStreamingSequence()
        assertEquals("Start streaming sequence should have 3 steps", 3, seq.size)
    }

    @Test
    fun startStreamingSequenceDelays() {
        val seq = Wt901Commander.startStreamingSequence()
        assertEquals(50L, seq[0].delayAfterMs)  // Unlock → 50ms
        assertEquals(100L, seq[1].delayAfterMs) // OutputContent → 100ms
        assertEquals(500L, seq[2].delayAfterMs) // Save → 500ms
    }

    @Test
    fun startStreamingSequenceCommandBytes() {
        val seq = Wt901Commander.startStreamingSequence()
        assertArrayEquals(Wt901Commander.unlock(), seq[0].bytes)
        assertArrayEquals(Wt901Commander.setOutputContent(0x0046), seq[1].bytes)
        assertArrayEquals(Wt901Commander.save(), seq[2].bytes)
    }

    @Test
    fun stopStreamingSequenceLength() {
        val seq = Wt901Commander.stopStreamingSequence()
        assertEquals("Stop streaming sequence should have 3 steps", 3, seq.size)
    }

    @Test
    fun stopStreamingSequenceDelays() {
        val seq = Wt901Commander.stopStreamingSequence()
        assertEquals(50L, seq[0].delayAfterMs)  // Unlock → 50ms
        assertEquals(100L, seq[1].delayAfterMs) // OutputContent disable → 100ms
        assertEquals(500L, seq[2].delayAfterMs) // Save → 500ms
    }

    @Test
    fun stopStreamingSequenceCommandBytes() {
        val seq = Wt901Commander.stopStreamingSequence()
        assertArrayEquals(Wt901Commander.unlock(), seq[0].bytes)
        assertArrayEquals(Wt901Commander.setOutputContent(0x0000), seq[1].bytes)
        assertArrayEquals(Wt901Commander.save(), seq[2].bytes)
    }
}
