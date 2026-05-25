package ru.skatelab.capture.domain.repository

import org.junit.Assert.assertEquals
import org.junit.Test

class BleRepositoryTest {
    // --- rawBatteryToPercent tests ---

    @Test
    fun rawBatteryToPercent_fullCharge() {
        assertEquals(100, BleRepository.rawBatteryToPercent(415))
        assertEquals(100, BleRepository.rawBatteryToPercent(420))
    }

    @Test
    fun rawBatteryToPercent_90percent() {
        assertEquals(90, BleRepository.rawBatteryToPercent(405))
        assertEquals(90, BleRepository.rawBatteryToPercent(414))
    }

    @Test
    fun rawBatteryToPercent_75percent() {
        assertEquals(75, BleRepository.rawBatteryToPercent(395))
        assertEquals(75, BleRepository.rawBatteryToPercent(404))
    }

    @Test
    fun rawBatteryToPercent_60percent() {
        assertEquals(60, BleRepository.rawBatteryToPercent(385))
        assertEquals(60, BleRepository.rawBatteryToPercent(394))
    }

    @Test
    fun rawBatteryToPercent_45percent() {
        assertEquals(45, BleRepository.rawBatteryToPercent(375))
        assertEquals(45, BleRepository.rawBatteryToPercent(384))
    }

    @Test
    fun rawBatteryToPercent_30percent() {
        assertEquals(30, BleRepository.rawBatteryToPercent(365))
        assertEquals(30, BleRepository.rawBatteryToPercent(374))
    }

    @Test
    fun rawBatteryToPercent_20percent() {
        assertEquals(20, BleRepository.rawBatteryToPercent(355))
        assertEquals(20, BleRepository.rawBatteryToPercent(364))
    }

    @Test
    fun rawBatteryToPercent_10percent() {
        assertEquals(10, BleRepository.rawBatteryToPercent(345))
        assertEquals(10, BleRepository.rawBatteryToPercent(354))
    }

    @Test
    fun rawBatteryToPercent_5percent() {
        assertEquals(5, BleRepository.rawBatteryToPercent(335))
        assertEquals(5, BleRepository.rawBatteryToPercent(344))
    }

    @Test
    fun rawBatteryToPercent_dead() {
        assertEquals(0, BleRepository.rawBatteryToPercent(334))
        assertEquals(0, BleRepository.rawBatteryToPercent(300))
        assertEquals(0, BleRepository.rawBatteryToPercent(0))
        assertEquals(0, BleRepository.rawBatteryToPercent(-1))
    }
}
