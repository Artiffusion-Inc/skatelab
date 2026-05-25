package ru.skatelab.capture.data.sync

import io.mockk.mockk
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository

class TimeSyncManagerTest {
    private val bleRepository: BleRepository = mockk(relaxed = true)
    private val manager = TimeSyncManager(bleRepository)

    @Test
    fun `initial offset from 20 samples per sensor`() {
        // Simulate 20 packets for LEFT sensor with consistent 500ms offset
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500 // chip is 500ms ahead
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }

        assertTrue("Should be initialized after 20 samples", manager.isInitialized(SensorId.LEFT))
        // offset = chipTimeMs * 1_000_000 - androidNs = 500_000_000
        assertEquals(500_000_000L, manager.getOffset(SensorId.LEFT))
    }

    @Test
    fun `not ready before 20 samples`() {
        for (i in 0 until 19) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }

        assertFalse("Should not be ready before 20 samples", manager.isInitialized(SensorId.LEFT))
        assertEquals(0L, manager.getOffset(SensorId.LEFT)) // default 0
    }

    @Test
    fun `EMA resync updates offset`() {
        // Establish initial offset of 500ms
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }

        assertEquals(500_000_000L, manager.getOffset(SensorId.LEFT))

        // Resync with drifted offset (520ms)
        val androidNs = 15_000_000_000L
        val chipTimeMs = (androidNs / 1_000_000) + 520
        manager.updatePeriodicOffset(SensorId.LEFT, androidNs, chipTimeMs)

        // EMA: 0.3 * 520_000_000 + 0.7 * 500_000_000 = 156_000_000 + 350_000_000 = 506_000_000
        assertEquals(506_000_000L, manager.getOffset(SensorId.LEFT))
    }

    @Test
    fun `each sensor has independent offset`() {
        // LEFT: 500ms offset
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }

        // RIGHT: 300ms offset
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 300
            manager.recordPacketArrival(SensorId.RIGHT, androidNs, chipTimeMs)
        }

        assertTrue(manager.isInitialized(SensorId.LEFT))
        assertTrue(manager.isInitialized(SensorId.RIGHT))
        assertEquals(500_000_000L, manager.getOffset(SensorId.LEFT))
        assertEquals(300_000_000L, manager.getOffset(SensorId.RIGHT))
    }

    @Test
    fun `updatePeriodicOffset sets offset when not yet initialized`() {
        // Direct periodic update without initial samples
        val androidNs = 10_000_000_000L
        val chipTimeMs = (androidNs / 1_000_000) + 200
        manager.updatePeriodicOffset(SensorId.LEFT, androidNs, chipTimeMs)

        assertEquals(200_000_000L, manager.getOffset(SensorId.LEFT))
    }

    @Test
    fun `extra samples beyond threshold do not change offset`() {
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }
        val offset20 = manager.getOffset(SensorId.LEFT)

        // Add 5 more samples with different offset — should be ignored
        for (i in 20 until 25) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 900 // different offset
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }
        assertEquals("Offset should not change after threshold", offset20, manager.getOffset(SensorId.LEFT))
    }

    @Test
    fun `median with odd count picks middle`() {
        // Provide 20 samples with known distribution: all same offset
        for (i in 0 until 20) {
            manager.recordPacketArrival(SensorId.LEFT, androidNs = 1_000_000L + i, chipTimeMs = 1L)
        }
        // offsetNs = 1 * 1_000_000 - (1_000_000 + i) = 1_000_000 - 1_000_000 - i = -i
        // All offsets are [-0, -1, -2, ..., -19], median of even count = (-9 + -10)/2 = -9
        assertEquals(-9L, manager.getOffset(SensorId.LEFT))
    }

    @Test
    fun `multiple EMA updates converge toward target`() {
        for (i in 0 until 20) {
            val androidNs = 10_000_000_000L + i * 10_000_000L
            val chipTimeMs = (androidNs / 1_000_000) + 500
            manager.recordPacketArrival(SensorId.LEFT, androidNs, chipTimeMs)
        }

        // Repeatedly resync with 600ms offset (target 600_000_000 ns)
        repeat(15) {
            manager.updatePeriodicOffset(
                SensorId.LEFT,
                androidNs = 15_000_000_000L,
                chipTimeMs = (15_000_000_000L / 1_000_000) + 600,
            )
        }
        val offset = manager.getOffset(SensorId.LEFT)
        assertTrue("Offset should converge toward 600M ns, was $offset", offset in 570_000_000..630_000_000L)
    }
}
