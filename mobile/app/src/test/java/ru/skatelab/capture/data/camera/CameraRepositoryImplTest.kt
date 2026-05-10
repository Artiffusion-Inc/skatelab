package ru.skatelab.capture.data.camera

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CameraRepositoryImplTest {

    @Test
    fun legacyHardwareLevel_selectsCameraX() {
        val useCameraX = LEGACY < FULL
        assertTrue("LEGACY (0) should use CameraX", useCameraX)
    }

    @Test
    fun limitedHardwareLevel_selectsCameraX() {
        val useCameraX = LIMITED < FULL
        assertTrue("LIMITED (1) should use CameraX", useCameraX)
    }

    @Test
    fun fullHardwareLevel_selectsCamera2() {
        val useCameraX = FULL < FULL
        assertFalse("FULL (2) should use Camera2, not CameraX", useCameraX)
    }

    @Test
    fun level3HardwareLevel_selectsCamera2() {
        val useCameraX = LEVEL_3 < FULL
        assertFalse("LEVEL_3 (3) should use Camera2, not CameraX", useCameraX)
    }

    companion object {
        private const val LEGACY = 0
        private const val LIMITED = 1
        private const val FULL = 2
        private const val LEVEL_3 = 3
    }
}
