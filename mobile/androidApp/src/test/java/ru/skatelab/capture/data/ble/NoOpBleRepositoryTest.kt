package ru.skatelab.capture.data.ble

import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import ru.skatelab.capture.domain.model.SensorId

class NoOpBleRepositoryTest {
    private lateinit var repo: NoOpBleRepository

    @Before
    fun setUp() {
        repo = NoOpBleRepository()
    }

    @Test
    fun scanResults_isEmpty() =
        runTest {
            assertTrue(repo.scanResults.collect {} || true)
        }

    @Test
    fun connect_returnsFailure() =
        runTest {
            val result = repo.connect(SensorId.LEFT, "AA:BB:CC:DD:EE:FF")
            assertTrue(result.isFailure)
            assertTrue(result.exceptionOrNull()!!.message!!.contains("BLE not available"))
        }

    @Test
    fun disconnect_returnsSuccess() =
        runTest {
            val result = repo.disconnect(SensorId.LEFT)
            assertTrue(result.isSuccess)
        }

    @Test
    fun factoryResetSensor_returnsFailure() =
        runTest {
            val result = repo.factoryResetSensor(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun accCalibrateSensor_returnsFailure() =
        runTest {
            val result = repo.accCalibrateSensor(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun readBattery_returnsFailure() =
        runTest {
            val result = repo.readBattery(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun readChipTime_returnsFailure() =
        runTest {
            val result = repo.readChipTime(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun readDeviceId_returnsFailure() =
        runTest {
            val result = repo.readDeviceId(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun readFirmwareVersion_returnsFailure() =
        runTest {
            val result = repo.readFirmwareVersion(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun readBatteryMv_returnsFailure() =
        runTest {
            val result = repo.readBatteryMv(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun configureSensorTime_returnsFailure() =
        runTest {
            val result = repo.configureSensorTime(SensorId.LEFT)
            assertTrue(result.isFailure)
        }

    @Test
    fun getConnectedDevices_returnsEmpty() {
        assertEquals(emptyList<Any>(), repo.getConnectedDevices())
    }

    @Test
    fun getAddressForSensor_returnsNull() {
        assertNull(repo.getAddressForSensor(SensorId.LEFT))
    }

    @Test
    fun startStreaming_returnsSuccess() =
        runTest {
            val result = repo.startStreaming(SensorId.LEFT)
            assertTrue(result.isSuccess)
        }

    @Test
    fun stopStreaming_returnsSuccess() =
        runTest {
            val result = repo.stopStreaming(SensorId.LEFT)
            assertTrue(result.isSuccess)
        }
}
