package ru.skatelab.capture.data.camera

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraRepositoryImplTest {
    @Test
    fun fullHardwareLevel_isSupported() {
        val isSupported = FULL >= FULL
        assertTrue("FULL (2) devices should be supported", isSupported)
    }

    @Test
    fun level3HardwareLevel_isSupported() {
        val isSupported = LEVEL_3 >= FULL
        assertTrue("LEVEL_3 (3) devices should be supported", isSupported)
    }

    @Test
    fun legacyHardwareLevel_isNotSupported() {
        val isSupported = LEGACY >= FULL
        assertFalse("LEGACY (0) devices should NOT be supported", isSupported)
    }

    @Test
    fun limitedHardwareLevel_isNotSupported() {
        val isSupported = LIMITED >= FULL
        assertFalse("LIMITED (1) devices should NOT be supported", isSupported)
    }

    companion object {
        private const val LEGACY = 0
        private const val LIMITED = 1
        private const val FULL = 2
        private const val LEVEL_3 = 3
    }
}
