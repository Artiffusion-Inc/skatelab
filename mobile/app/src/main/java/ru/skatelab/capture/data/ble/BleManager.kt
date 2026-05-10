package ru.skatelab.capture.data.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.util.Log
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.SystemClock
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit

/**
 * Manages BLE scanning, connections, and communication with WT901 sensors.
 *
 * Key characteristics:
 * - Scans with ServiceUUID FFE5 filter
 * - Uses WRITE_TYPE_NO_RESPONSE for FFE9 write characteristic
 * - Parses IMU data on a dedicated [BleHandlerThread]
 * - Re-requests CONNECTION_PRIORITY_HIGH every 30 seconds
 * - Serializes GATT write operations with inter-command delays
 */
class BleManager(private val context: Context, private val logger: ru.skatelab.capture.AppLogger? = null) {

    private fun logi(msg: String) { Log.i(TAG, msg); logger?.i(TAG, msg) }
    private fun logw(msg: String) { Log.w(TAG, msg); logger?.w(TAG, msg) }
    private fun loge(msg: String) { Log.e(TAG, msg); logger?.e(TAG, msg) }

    companion object {
        private const val TAG = "BleManager"
        // WT901 BLE UUIDs
        val SERVICE_UUID: UUID = UUID.fromString("0000FFE5-0000-1000-8000-00805F9A34FB")
        val NOTIFY_UUID: UUID = UUID.fromString("0000FFE4-0000-1000-8000-00805F9A34FB")
        val WRITE_UUID: UUID = UUID.fromString("0000FFE9-0000-1000-8000-00805F9A34FB")
        val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805F9A34FB")

        private const val REPRIORITY_INTERVAL_MS = 30_000L
    }

    private val bluetoothAdapter: BluetoothAdapter? =
        (context.getSystemService(Context.BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager)
            ?.adapter

    private val handlerThread = BleHandlerThread()

    // Active GATT connections keyed by sensor address
    private val gattConnections = ConcurrentHashMap<String, BluetoothGatt>()
    private val writeCharacteristics = ConcurrentHashMap<String, BluetoothGattCharacteristic>()
    private val notifyCharacteristics = ConcurrentHashMap<String, BluetoothGattCharacteristic>()

    // Flows for scan results, connection state, and IMU samples
    private val _scanResults = MutableStateFlow<List<ScanResult>>(emptyList())
    val scanResults: Flow<List<ScanResult>> = _scanResults.asStateFlow()

    private val _connectionState = MutableStateFlow<Map<SensorId, ConnectionState>>(emptyMap())
    val connectionState: Flow<Map<SensorId, ConnectionState>> = _connectionState.asStateFlow()

    private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 64)
    val imuSamples: Flow<Pair<SensorId, ImuSample>> = _imuSamples.asSharedFlow()

    // Map sensor address to SensorId (assigned by user during scan)
    private val addressToSensorId = ConcurrentHashMap<String, SensorId>()

    // Re-priority timer per sensor
    private val repriorityTimers = ConcurrentHashMap<String, Long>()

    // --- Scanning ---

    @SuppressLint("MissingPermission")
    fun startScan() {
        val adapter = bluetoothAdapter ?: run { loge("No BluetoothAdapter"); return }
        val scanner = adapter.bluetoothLeScanner ?: run { loge("No BLE scanner"); return }
        logi("Starting BLE scan with filter $SERVICE_UUID")

        val filter = android.bluetooth.le.ScanFilter.Builder()
            .setServiceUuid(android.os.ParcelUuid.fromString(SERVICE_UUID.toString()))
            .build()

        val settings = android.bluetooth.le.ScanSettings.Builder()
            .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        val foundDevices = mutableMapOf<String, ScanResult>()

        scanner.startScan(listOf(filter), settings, object : android.bluetooth.le.ScanCallback() {
            override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult) {
                val device = result.device
                logi("Scan result: ${device.name} @ ${device.address} RSSI=${result.rssi}")
                val name = device.name ?: "WT901"
                val address = device.address
                foundDevices[address] = ScanResult(name, address, result.rssi)
                _scanResults.value = foundDevices.values.toList()
            }

            override fun onScanFailed(errorCode: Int) {
                loge("BLE scan failed: errorCode=$errorCode")
            }
        })
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        bluetoothAdapter?.bluetoothLeScanner?.stopScan(object : android.bluetooth.le.ScanCallback() {
            override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult) {}
        })
    }

    // --- Connection ---

    @SuppressLint("MissingPermission")
    suspend fun connect(sensorId: SensorId, address: String): Result<Unit> {
        val adapter = bluetoothAdapter ?: return Result.failure(IllegalStateException("No BluetoothAdapter"))
        val device = adapter.getRemoteDevice(address) ?: return Result.failure(IllegalArgumentException("Device not found: $address"))

        addressToSensorId[address] = sensorId
        updateConnectionState(sensorId, ConnectionState.CONNECTING)

        if (!handlerThread.isAlive) {
            handlerThread.start()
            handlerThread.prepareHandler()
        }

        device.connectGatt(context, false, createGattCallback(sensorId, address))

        // Wait for CONNECTED state (onServicesDiscovered completes)
        val connected = withTimeoutOrNull(10_000L) {
            _connectionState.first { it[sensorId] == ConnectionState.CONNECTED || it[sensorId] == ConnectionState.DISCONNECTED }
        }

        val state = _connectionState.value[sensorId]
        return if (state == ConnectionState.CONNECTED) {
            logi("Sensor $sensorId connected and ready")
            Result.success(Unit)
        } else {
            loge("Sensor $sensorId connection failed or timeout, state=$state")
            Result.failure(IllegalStateException("Connection failed for $sensorId, state=$state"))
        }
    }

    @SuppressLint("MissingPermission")
    fun disconnect(sensorId: SensorId, address: String) {
        val gatt = gattConnections.remove(address) ?: return
        writeCharacteristics.remove(address)
        notifyCharacteristics.remove(address)
        handlerThread.removeParser(address)
        addressToSensorId.remove(address)
        repriorityTimers.remove(address)
        gatt.disconnect()
        gatt.close()
        updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
    }

    // --- GATT Callback ---

    @SuppressLint("MissingPermission")
    private fun createGattCallback(sensorId: SensorId, address: String) = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            logi("GATT state change: address=$address status=$status newState=$newState")
            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gattConnections[address] = gatt
                gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                gatt.discoverServices()
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                gattConnections.remove(address)
                updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            logi("Services discovered: address=$address status=$status")
            if (status != BluetoothGatt.GATT_SUCCESS) return

            val service = gatt.getService(SERVICE_UUID)
            if (service == null) {
                loge("Service $SERVICE_UUID not found for $address")
                gatt.disconnect()
                return
            }

            // Subscribe to IMU notifications (FFE4)
            val notifyChar = service.getCharacteristic(NOTIFY_UUID)
            if (notifyChar == null) {
                loge("Notify char $NOTIFY_UUID not found for $address")
                gatt.disconnect()
                return
            }
            notifyCharacteristics[address] = notifyChar
            gatt.setCharacteristicNotification(notifyChar, true)

            // Write CCCD descriptor to enable notifications.
            // WT901 uses non-standard CCCD UUID (9b34fb vs 9a34fb), so find by descriptor 0x2902 prefix.
            val descriptor = notifyChar.descriptors.find {
                it.uuid.toString().startsWith("00002902")
            }
            if (descriptor != null) {
                descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                gatt.writeDescriptor(descriptor)
                logi("CCCD descriptor write requested for $address (uuid=${descriptor.uuid})")
            } else {
                logw("No CCCD descriptor found for $NOTIFY_UUID — completing setup")
                completeSetup(gatt, address, sensorId)
            }

            // Get write characteristic (FFE9) — store for later use
            val writeChar = service.getCharacteristic(WRITE_UUID)
            if (writeChar == null) {
                loge("Write char $WRITE_UUID not found for $address")
                gatt.disconnect()
                return
            }
            writeChar.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
            writeCharacteristics[address] = writeChar
        }

        private var imuPacketCount = 0L

        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            if (characteristic.uuid != NOTIFY_UUID) return

            // IMMEDIATE copy — characteristic value buffer is reused by the BLE stack
            val bytes = characteristic.value.copyOf()
            val arrivalNs = SystemClock.elapsedRealtimeNanos()

            // Re-request high priority every 30 seconds
            reRequestHighPriority(gatt, address)

            // Periodic packet counter log (every 500 packets ≈ every 5s at 100Hz)
            imuPacketCount++
            if (imuPacketCount % 500 == 0L) {
                logi("IMU packets: $imuPacketCount from $address")
            }

            // Offload parsing to handler thread
            handlerThread.postParsing(bytes, address) { sample ->
                if (sample != null) {
                    val id = addressToSensorId[address] ?: return@postParsing
                    _imuSamples.tryEmit(id to sample)
                }
            }
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            logi("onDescriptorWrite: $address uuid=${descriptor.uuid} status=$status")
            if (descriptor.uuid.toString().startsWith("00002902")) {
                completeSetup(gatt, address, sensorId)
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun completeSetup(gatt: BluetoothGatt, address: String, sensorId: SensorId) {
        updateConnectionState(sensorId, ConnectionState.CONNECTED)
        logi("Sensor $sensorId CONNECTED, notify+write chars ready")
    }

    // --- Command Sending ---

    @SuppressLint("MissingPermission")
    fun sendCommand(sensorId: SensorId, bytes: ByteArray) {
        val address = addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
            logw("sendCommand: no address for $sensorId"); return
        }
        val gatt = gattConnections[address] ?: run {
            logw("sendCommand: no GATT for $address"); return
        }
        val char = writeCharacteristics[address] ?: run {
            logw("sendCommand: no write char for $address"); return
        }
        char.value = bytes
        val success = gatt.writeCharacteristic(char)
        logi("writeCharacteristic $sensorId: ${bytes.joinToString("") { "%02x".format(it) }} success=$success")
    }

    /**
     * Send a sequence of command steps with inter-command delays.
     * Delays are implemented via Thread.sleep on the handler thread.
     */
    fun sendSequence(sensorId: SensorId, steps: List<Wt901Commander.CommandStep>) {
        val address = addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
            logw("sendSequence: no address for $sensorId"); return
        }
        logi("sendSequence: $sensorId steps=${steps.size}")
        handlerThread.handler?.post {
            // Small delay after CCCD write before sending commands
            Thread.sleep(100L)
            for ((index, step) in steps.withIndex()) {
                sendCommand(sensorId, step.bytes)
                if (step.delayAfterMs > 0) {
                    Thread.sleep(step.delayAfterMs)
                }
            }
            logi("sendSequence complete: $sensorId")
        }
    }

    // --- Priority Management ---

    @SuppressLint("MissingPermission")
    private fun reRequestHighPriority(gatt: BluetoothGatt, address: String) {
        val now = SystemClock.elapsedRealtimeNanos()
        val lastRequest = repriorityTimers[address] ?: 0L
        if (now - lastRequest > TimeUnit.MILLISECONDS.toNanos(REPRIORITY_INTERVAL_MS)) {
            gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
            repriorityTimers[address] = now
        }
    }

    private fun updateConnectionState(sensorId: SensorId, state: ConnectionState) {
        val current = _connectionState.value.toMutableMap()
        current[sensorId] = state
        _connectionState.value = current
    }

    // --- Inner types ---

    data class ScanResult(val name: String, val address: String, val rssi: Int)

    enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }
}
