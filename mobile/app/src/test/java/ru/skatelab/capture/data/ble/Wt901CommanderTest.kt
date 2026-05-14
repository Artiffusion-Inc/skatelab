package ru.skatelab.capture.data.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class Wt901CommanderTest {
    // --- Atomic command byte format tests ---

    @Test
    fun unlockCommand() {
        val bytes = Wt901Commander.unlock()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x69, 0x88.toByte(), 0xB5.toByte()),
            bytes,
        )
    }

    @Test
    fun setRateCommand() {
        val bytes = Wt901Commander.setRate(0x09)
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

    @Test
    fun accCalibrateCommand() {
        val bytes = Wt901Commander.accCalibrate()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x01, 0x01, 0x00),
            bytes,
        )
    }

    @Test
    fun stopCalibrationCommand() {
        val bytes = Wt901Commander.stopCalibration()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x01, 0x00, 0x00),
            bytes,
        )
    }

    @Test
    fun wakeUpCommand() {
        val bytes = Wt901Commander.wakeUp()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xF0.toByte(), 0xF0.toByte(), 0xF0.toByte(), 0xF0.toByte()),
            bytes,
        )
    }

    @Test
    fun factoryResetCommand() {
        val bytes = Wt901Commander.factoryReset()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x00, 0x01, 0x00),
            bytes,
        )
    }

    @Test
    fun restartCommand() {
        val bytes = Wt901Commander.restart()
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x00, 0xFF.toByte(), 0x00),
            bytes,
        )
    }

    // --- Sequence tests ---

    @Test
    fun bleAccCalibrateSequenceLength() {
        val seq = Wt901Commander.bleAccCalibrateSequence()
        assertEquals("ACC calibrate sequence should have 6 steps", 6, seq.size)
    }

    @Test
    fun bleAccCalibrateSequenceDelays() {
        val seq = Wt901Commander.bleAccCalibrateSequence()
        assertEquals(100L, seq[0].delayAfterMs) // stopCalib → 100ms
        assertEquals(50L, seq[1].delayAfterMs) // unlock → 50ms
        assertEquals(2000L, seq[2].delayAfterMs) // stopCalib(working) → 2000ms
        assertEquals(50L, seq[3].delayAfterMs) // unlock → 50ms
        assertEquals(2000L, seq[4].delayAfterMs) // accCalibrate → 2000ms
        assertEquals(500L, seq[5].delayAfterMs) // save → 500ms
    }

    @Test
    fun bleAccCalibrateSequenceCommandBytes() {
        val seq = Wt901Commander.bleAccCalibrateSequence()
        assertArrayEquals(Wt901Commander.stopCalibration(), seq[0].bytes)
        assertArrayEquals(Wt901Commander.unlock(), seq[1].bytes)
        assertArrayEquals(Wt901Commander.stopCalibration(), seq[2].bytes)
        assertArrayEquals(Wt901Commander.unlock(), seq[3].bytes)
        assertArrayEquals(Wt901Commander.accCalibrate(), seq[4].bytes)
        assertArrayEquals(Wt901Commander.save(), seq[5].bytes)
    }

    @Test
    fun bleAccCalibrateWithWakeSequenceLength() {
        val seq = Wt901Commander.bleAccCalibrateWithWakeSequence()
        assertEquals("ACC calibrate+wake sequence should have 6 steps", 6, seq.size)
    }

    @Test
    fun bleAccCalibrateWithWakeSequenceDelays() {
        val seq = Wt901Commander.bleAccCalibrateWithWakeSequence()
        assertEquals(100L, seq[0].delayAfterMs) // wakeUp → 100ms
        assertEquals(50L, seq[1].delayAfterMs) // unlock → 50ms
        assertEquals(2000L, seq[2].delayAfterMs) // stopCalib → 2000ms
        assertEquals(50L, seq[3].delayAfterMs) // unlock → 50ms
        assertEquals(2000L, seq[4].delayAfterMs) // accCalibrate → 2000ms
        assertEquals(500L, seq[5].delayAfterMs) // save → 500ms
    }

    @Test
    fun bleAccCalibrateWithWakeSequenceCommandBytes() {
        val seq = Wt901Commander.bleAccCalibrateWithWakeSequence()
        assertArrayEquals(Wt901Commander.wakeUp(), seq[0].bytes)
        assertArrayEquals(Wt901Commander.unlock(), seq[1].bytes)
        assertArrayEquals(Wt901Commander.stopCalibration(), seq[2].bytes)
        assertArrayEquals(Wt901Commander.unlock(), seq[3].bytes)
        assertArrayEquals(Wt901Commander.accCalibrate(), seq[4].bytes)
        assertArrayEquals(Wt901Commander.save(), seq[5].bytes)
    }

    // --- Time config command tests ---

    @Test
    fun setTimeYearMonthCommand() {
        val bytes = Wt901Commander.setTimeYearMonth(2026, 5)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x30, 0x05, (2026 - 2000).toByte()),
            bytes,
        )
    }

    @Test
    fun setTimeHourDayCommand() {
        val bytes = Wt901Commander.setTimeHourDay(14, 15)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x31, 14, 15),
            bytes,
        )
    }

    @Test
    fun setTimeSecondMinuteCommand() {
        val bytes = Wt901Commander.setTimeSecondMinute(30, 45)
        assertArrayEquals(
            byteArrayOf(0xFF.toByte(), 0xAA.toByte(), 0x32, 30, 45),
            bytes,
        )
    }

    @Test
    fun timeConfigSequenceLength() {
        val seq = Wt901Commander.timeConfigSequence()
        assertEquals("Time config sequence should have 5 steps", 5, seq.size)
    }

    @Test
    fun timeConfigSequenceContainsCorrectCommands() {
        val seq = Wt901Commander.timeConfigSequence()
        assertArrayEquals(Wt901Commander.unlock(), seq[0].bytes)
        // Steps 1-3 are time-set commands (bytes vary by current time)
        assertArrayEquals(Wt901Commander.save(), seq[4].bytes)
    }

    @Test
    fun timeConfigSequenceDelays() {
        val seq = Wt901Commander.timeConfigSequence()
        assertEquals(50L, seq[0].delayAfterMs) // unlock → 50ms
        assertEquals(100L, seq[1].delayAfterMs) // setTimeYearMonth → 100ms
        assertEquals(100L, seq[2].delayAfterMs) // setTimeHourDay → 100ms
        assertEquals(100L, seq[3].delayAfterMs) // setTimeSecondMinute → 100ms
        assertEquals(500L, seq[4].delayAfterMs) // save → 500ms
    }
}
