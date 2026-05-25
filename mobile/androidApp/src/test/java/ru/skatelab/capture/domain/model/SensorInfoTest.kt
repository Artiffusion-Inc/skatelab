package ru.skatelab.capture.domain.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class SensorInfoTest {
    @Test
    fun equals_sameValues_returnsTrue() {
        val a = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        val b = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        assertEquals(a, b)
    }

    @Test
    fun equals_differentDeviceId_returnsFalse() {
        val a = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        val b = SensorInfo(deviceId = "WT901-XYZ", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        assertNotEquals(a, b)
    }

    @Test
    fun equals_differentBattery_returnsFalse() {
        val a = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        val b = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 50, batteryMv = 3700)
        assertNotEquals(a, b)
    }

    @Test
    fun copy_modifiesField() {
        val a = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        val b = a.copy(batteryPercent = 90)
        assertEquals(90, b.batteryPercent)
        assertEquals(85, a.batteryPercent)
    }

    @Test
    fun hashCode_sameValues_returnsSameHashCode() {
        val a = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        val b = SensorInfo(deviceId = "WT901-ABC", firmwareVersion = "3.1.2", batteryPercent = 85, batteryMv = 3700)
        assertEquals(a.hashCode(), b.hashCode())
    }
}
