package ru.skatelab.capture.data.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import android.util.Log
import java.util.Collections
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId

/**
 * Manages BLE scanning, connections, and communication with WT901 sensors.
 *
 * Based on WT901BLECL reference pattern:
 * - Connect → discoverServices → enable CCCD → setRate(0x09) after 1s
 * - NO unlock/save/accCalibrate on connect (proven to corrupt ACC offset)
 * - Single HandlerThread for writes + parsing
 * - 0x61 frame streams automatically when CCCD is enabled
 *
 * See: docs/specs/2026-05-14-ble-stack-redesign-design.md
 */
class BleManager(
    private val context: Context,
    private val logger: ru.skatelab.capture.AppLogger? = null,
) {
    private fun logi(msg: String) {
        Log.i(TAG, msg)
        logger?.i(TAG, msg)
    }

    private fun logw(msg: String) {
        Log.w(TAG, msg)
        logger?.w(TAG, msg)
    }

    private fun loge(msg: String) {
        Log.e(TAG, msg)
        logger?.e(TAG, msg)
    }

    private val readMutex = Mutex()

    companion object {
        private const val TAG = "BleManager"
        val SERVICE_UUID: UUID = UUID.fromString("0000FFE5-0000-1000-8000-00805F9A34FB")
        val NOTIFY_UUID: UUID = UUID.fromString("0000FFE4-0000-1000-8000-00805F9A34FB")
        val WRITE_UUID: UUID = UUID.fromString("0000FFE9-0000-1000-8000-00805F9A34FB")
        val CCCD_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805F9A34FB")
        private const val REPRIORITY_INTERVAL_MS = 30_000L
        private const val SET_RATE_DELAY_MS = 1000L
        private const val DEFAULT_RATE = 0x09 // 100Hz
    }

    private val bluetoothAdapter: BluetoothAdapter? =
        (context.getSystemService(Context.BLUETOOTH_SERVICE) as? android.bluetooth.BluetoothManager)
            ?.adapter

    // Single HandlerThread for all GATT writes + parsing (like WT901BLECL reference)
    private val workThread = HandlerThread("BLE-Work").apply { start() }
    private val workHandler = Handler(workThread.looper)

    // Per-device state
    private val gatts = ConcurrentHashMap<String, BluetoothGatt>()
    private val parsers = ConcurrentHashMap<String, Wt901Parser>()
    private val writeChars = ConcurrentHashMap<String, BluetoothGattCharacteristic>()
    private val notifyChars = ConcurrentHashMap<String, BluetoothGattCharacteristic>()
    private val addressToSensorId = ConcurrentHashMap<String, SensorId>()

    // Re-priority timer per sensor
    private val repriorityTimers = ConcurrentHashMap<String, Long>()

    // Recording state for auto-reconnect guard
    private val recordingSensors: MutableSet<SensorId> = ConcurrentHashMap.newKeySet()

    // Flows
    private val _scanResults = MutableStateFlow<List<ScanResult>>(emptyList())
    val scanResults: Flow<List<ScanResult>> = _scanResults.asStateFlow()

    private val _connectionState = MutableStateFlow<Map<SensorId, ConnectionState>>(emptyMap())
    val connectionState: Flow<Map<SensorId, ConnectionState>> = _connectionState.asStateFlow()

    private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 1024)
    val imuSamples: Flow<Pair<SensorId, ImuSample>> = _imuSamples.asSharedFlow()

    private val _registerReadResults = MutableSharedFlow<Pair<String, RegisterReadResult>>(extraBufferCapacity = 8)
    val registerReadResults: Flow<Pair<String, RegisterReadResult>> = _registerReadResults.asSharedFlow()

    private val _reconnectEvents = MutableSharedFlow<SensorId>(extraBufferCapacity = 8)
    val reconnectEvents: Flow<SensorId> = _reconnectEvents.asSharedFlow()

    @Volatile
    private var activeScanCallback: android.bluetooth.le.ScanCallback? = null

    fun markRecording(sensorId: SensorId) {
        recordingSensors.add(sensorId)
    }

    fun markStopped(sensorId: SensorId) {
        recordingSensors.remove(sensorId)
    }

    fun isRecording(sensorId: SensorId): Boolean = sensorId in recordingSensors

    // --- Scanning ---

    @SuppressLint("MissingPermission")
    fun startScan() {
        val adapter =
            bluetoothAdapter ?: run {
                loge("No BluetoothAdapter")
                return
            }
        val scanner =
            adapter.bluetoothLeScanner ?: run {
                loge("No BLE scanner")
                return
            }
        logi("Starting BLE scan with filter $SERVICE_UUID")

        _scanResults.value = emptyList()

        val filter =
            android.bluetooth.le.ScanFilter.Builder()
                .setServiceUuid(android.os.ParcelUuid.fromString(SERVICE_UUID.toString()))
                .build()

        val settings =
            android.bluetooth.le.ScanSettings.Builder()
                .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_LOW_LATENCY)
                .build()

        val foundDevices = Collections.synchronizedMap(mutableMapOf<String, ScanResult>())

        val callback =
            object : android.bluetooth.le.ScanCallback() {
                override fun onScanResult(
                    callbackType: Int,
                    result: android.bluetooth.le.ScanResult,
                ) {
                    try {
                        val device = result.device
                        logi("Scan result: ${device.name} @ ${device.address} RSSI=${result.rssi}")
                        val name = device.name ?: "WT901"
                        foundDevices[result.device.address] = ScanResult(name, device.address, result.rssi)
                        _scanResults.value = foundDevices.values.toList()
                    } catch (e: Exception) {
                        loge("ScanCallback error: ${e.message}")
                    }
                }

                override fun onScanFailed(errorCode: Int) {
                    loge("BLE scan failed: errorCode=$errorCode")
                }
            }
        activeScanCallback = callback
        scanner.startScan(listOf(filter), settings, callback)
    }

    @SuppressLint("MissingPermission")
    fun stopScan() {
        val callback = activeScanCallback ?: return
        bluetoothAdapter?.bluetoothLeScanner?.stopScan(callback)
        activeScanCallback = null
    }

    @SuppressLint("MissingPermission")
    fun getConnectedDevices(): List<ScanResult> =
        gatts.map { (address, gatt) ->
            val device = gatt.device
            val name = device.name ?: "WT901"
            ScanResult(name, address, 0)
        }

    // --- Connection ---

    @SuppressLint("MissingPermission")
    suspend fun connect(
        sensorId: SensorId,
        address: String,
    ): Result<Unit> {
        val adapter = bluetoothAdapter ?: return Result.failure(IllegalStateException("No BluetoothAdapter"))
        val device =
            adapter.getRemoteDevice(address)
                ?: return Result.failure(IllegalArgumentException("Device not found: $address"))

        addressToSensorId[address] = sensorId
        updateConnectionState(sensorId, ConnectionState.CONNECTING)

        device.connectGatt(context, false, createGattCallback(sensorId, address))

        // Wait for CONNECTED (setRate sent after CCCD enable + 1s delay)
        val connected =
            withTimeoutOrNull(15_000L) {
                _connectionState.first { it[sensorId] == ConnectionState.CONNECTED || it[sensorId] == ConnectionState.DISCONNECTED }
            }

        val state = _connectionState.value[sensorId]
        return if (state == ConnectionState.CONNECTED) {
            logi("Sensor $sensorId connected and ready")
            Result.success(Unit)
        } else {
            loge("Sensor $sensorId connection failed or timeout, state=$state")
            cleanupDevice(address, sensorId)
            Result.failure(IllegalStateException("Connection failed for $sensorId, state=$state"))
        }
    }

    @SuppressLint("MissingPermission")
    fun disconnect(
        sensorId: SensorId,
        address: String,
    ) {
        logi("Disconnecting $sensorId ($address)")
        cleanupDevice(address, sensorId)
    }

    @SuppressLint("MissingPermission")
    private fun cleanupDevice(
        address: String,
        sensorId: SensorId,
    ) {
        parsers.remove(address)
        writeChars.remove(address)
        notifyChars.remove(address)
        addressToSensorId.remove(address)
        repriorityTimers.remove(address)
        recordingSensors.remove(sensorId)
        gatts.remove(address)?.let { gatt ->
            gatt.disconnect()
            gatt.close()
        }
        updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
    }

    // --- GATT Callback ---

    @SuppressLint("MissingPermission")
    private fun createGattCallback(
        sensorId: SensorId,
        address: String,
    ): BluetoothGattCallback =
        object : BluetoothGattCallback() {
            private var imuPacketCount = 0L

            override fun onConnectionStateChange(
                gatt: BluetoothGatt,
                status: Int,
                newState: Int,
            ) {
                logi("GATT state change: $address status=$status newState=$newState")

                if (status == 133 && newState == BluetoothProfile.STATE_DISCONNECTED) {
                    logw("GATT error 133 for $address — closing stale GATT object")
                    gatts.remove(address)
                    gatt.close()
                    updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                    return
                }

                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    gatts[address] = gatt
                    gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                    workHandler.post { gatt.discoverServices() }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    gatts.remove(address)
                    gatt.close()

                    // Auto-reconnect if recording
                    if (sensorId in recordingSensors) {
                        logw("BLE disconnected during recording, reconnecting: $address")
                        updateConnectionState(sensorId, ConnectionState.RECONNECTING)
                        _reconnectEvents.tryEmit(sensorId)
                        workHandler.postDelayed({
                            try {
                                val device: BluetoothDevice = gatt.device
                                device.connectGatt(context, false, createGattCallback(sensorId, address))
                            } catch (e: Exception) {
                                loge("Reconnect failed: ${e.message}")
                                updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                            }
                        }, 2000L)
                    } else {
                        updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                    }
                }
            }

            override fun onServicesDiscovered(
                gatt: BluetoothGatt,
                status: Int,
            ) {
                if (status != BluetoothGatt.GATT_SUCCESS) {
                    loge("Service discovery failed: $address status=$status")
                    return
                }
                logi("Services discovered: $address")

                val service = gatt.getService(SERVICE_UUID)
                if (service == null) {
                    loge("Service $SERVICE_UUID not found for $address")
                    gatt.disconnect()
                    return
                }

                // Get write characteristic (FFE9) — store for later use
                val writeChar = service.getCharacteristic(WRITE_UUID)
                if (writeChar == null) {
                    loge("Write char $WRITE_UUID not found for $address")
                    gatt.disconnect()
                    return
                }
                writeChar.writeType = BluetoothGattCharacteristic.WRITE_TYPE_NO_RESPONSE
                writeChars[address] = writeChar

                // Subscribe to notifications (FFE4)
                val notifyChar = service.getCharacteristic(NOTIFY_UUID)
                if (notifyChar == null) {
                    loge("Notify char $NOTIFY_UUID not found for $address")
                    gatt.disconnect()
                    return
                }
                notifyChars[address] = notifyChar
                gatt.setCharacteristicNotification(notifyChar, true)

                // Write CCCD descriptor to enable notifications
                val descriptor =
                    notifyChar.descriptors.find {
                        it.uuid.toString().startsWith("00002902")
                    }
                if (descriptor != null) {
                    @Suppress("DEPRECATION")
                    descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                    @Suppress("DEPRECATION")
                    gatt.writeDescriptor(descriptor)
                    logi("CCCD descriptor write requested for $address")
                } else {
                    logw("No CCCD descriptor found — completing setup without notifications")
                    scheduleSetRateAndComplete(gatt, address, sensorId)
                }
            }

            override fun onDescriptorWrite(
                gatt: BluetoothGatt,
                descriptor: BluetoothGattDescriptor,
                status: Int,
            ) {
                logi("onDescriptorWrite: $address uuid=${descriptor.uuid} status=$status")
                if (descriptor.uuid.toString().startsWith("00002902")) {
                    if (status == BluetoothGatt.GATT_SUCCESS) {
                        scheduleSetRateAndComplete(gatt, address, sensorId)
                    } else {
                        loge("CCCD write failed (status=$status) for $address")
                        gatt.disconnect()
                    }
                }
            }

            override fun onCharacteristicChanged(
                gatt: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
            ) {
                if (characteristic.uuid != NOTIFY_UUID) return

                // IMMEDIATE copy — BLE stack reuses buffer
                @Suppress("DEPRECATION")
                val bytes = characteristic.value.copyOf()
                val arrivalNs = SystemClock.elapsedRealtimeNanos()

                reRequestHighPriority(gatt, address)

                imuPacketCount++
                if (imuPacketCount % 500 == 0L) {
                    logi("IMU packets: $imuPacketCount from $address")
                }

                // Parse on work thread (arrivalNs captured on Binder thread)
                workHandler.post {
                    val parser =
                        parsers.getOrPut(address) {
                            Wt901Parser().also {
                                it.logTag = "Wt901Parse-${address.takeLast(5)}"
                                it.onRegisterRead = { result ->
                                    _registerReadResults.tryEmit(address to result)
                                }
                            }
                        }
                    val samples = parser.feed(bytes, arrivalNs)
                    if (samples.isNotEmpty()) {
                        val id = addressToSensorId[address]
                        if (id != null) {
                            samples.forEach { sample ->
                                _imuSamples.tryEmit(id to sample)
                            }
                        } else {
                            logw("No SensorId for address=$address")
                        }
                    }
                }
            }
        }

    /**
     * After CCCD is enabled, schedule setRate(0x09) after 1s delay,
     * then mark sensor as CONNECTED.
     * This matches the WT901BLECL reference pattern exactly.
     */
    @SuppressLint("MissingPermission")
    private fun scheduleSetRateAndComplete(
        gatt: BluetoothGatt,
        address: String,
        sensorId: SensorId,
    ) {
        workHandler.postDelayed({
            try {
                val char = writeChars[address]
                if (char != null && gatts[address] != null) {
                    @Suppress("DEPRECATION")
                    char.value = Wt901Commander.setRate(DEFAULT_RATE)
                    @Suppress("DEPRECATION")
                    val success = gatt.writeCharacteristic(char)
                    logi("setRate(0x09) sent to $address, success=$success")
                } else {
                    logw("setRate: write char or gatt gone for $address")
                }
            } catch (e: Exception) {
                loge("setRate failed: ${e.message}")
            }
            updateConnectionState(sensorId, ConnectionState.CONNECTED)
            logi("Sensor $sensorId CONNECTED — setRate sent, data streaming")
        }, SET_RATE_DELAY_MS)
    }

    // --- Command Sending ---

    /**
     * Write raw bytes to a sensor's write characteristic.
     * Routes through workHandler for thread-safe GATT access.
     */
    @SuppressLint("MissingPermission")
    fun writeBytes(
        address: String,
        bytes: ByteArray,
    ) {
        workHandler.post {
            val char = writeChars[address]
            val gatt = gatts[address]
            if (char == null || gatt == null) {
                logw("writeBytes: no char/gatt for $address")
                return@post
            }
            @Suppress("DEPRECATION")
            char.value = bytes
            @Suppress("DEPRECATION")
            val success = gatt.writeCharacteristic(char)
            logi("writeBytes $address: ${bytes.joinToString("") { "%02x".format(it) }} success=$success")
        }
    }

    /**
     * Send a sequence of command steps with inter-command delays.
     * All writes are serialized through workHandler.
     */
    suspend fun writeSequence(
        address: String,
        steps: List<Wt901Commander.CommandStep>,
    ) {
        logi("writeSequence: $address steps=${steps.size}")
        kotlinx.coroutines.delay(100L)
        for ((index, step) in steps.withIndex()) {
            writeBytes(address, step.bytes)
            kotlinx.coroutines.delay(maxOf(step.delayAfterMs, 30L))
            logi("writeSequence step $index/${steps.size} sent")
        }
        logi("writeSequence complete: $address")
    }

    /**
     * Send a register read command and wait for the 0x71 response.
     */
    suspend fun readRegisterResponse(
        sensorId: SensorId,
        register: Int,
        timeoutMs: Long = 2000L,
    ): Result<ShortArray> =
        readMutex.withLock {
            val address =
                addressToSensorId.entries.find { it.value == sensorId }?.key
                    ?: return Result.failure(IllegalArgumentException("No address for $sensorId"))

            writeBytes(address, Wt901Commander.readRegister(register))

            try {
                val result =
                    withTimeoutOrNull(timeoutMs) {
                        _registerReadResults.first { (addr, r) ->
                            addr == address && r.register == register
                        }.second
                    }
                if (result != null) {
                    logi("readRegisterResponse: reg=0x${register.toString(16)} data=${result.data.toList()}")
                    Result.success(result.data)
                } else {
                    logw("readRegisterResponse: timeout for reg=0x${register.toString(16)}")
                    Result.failure(
                        java.util.concurrent.TimeoutException(
                            "No 0x71 response for register 0x${register.toString(16)} within ${timeoutMs}ms",
                        ),
                    )
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                loge("readRegisterResponse error: ${e.message}")
                Result.failure(e)
            }
        }

    /**
     * Convenience: send command by SensorId (finds address internally).
     */
    fun sendCommand(
        sensorId: SensorId,
        bytes: ByteArray,
    ) {
        val address =
            addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
                logw("sendCommand: no address for $sensorId")
                return
            }
        writeBytes(address, bytes)
    }

    /**
     * Convenience: send sequence by SensorId.
     */
    suspend fun sendSequence(
        sensorId: SensorId,
        steps: List<Wt901Commander.CommandStep>,
    ) {
        val address =
            addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
                logw("sendSequence: no address for $sensorId")
                return
            }
        writeSequence(address, steps)
    }

    // --- Priority Management ---

    @SuppressLint("MissingPermission")
    private fun reRequestHighPriority(
        gatt: BluetoothGatt,
        address: String,
    ) {
        val now = SystemClock.elapsedRealtimeNanos()
        val lastRequest = repriorityTimers[address] ?: 0L
        if (now - lastRequest > TimeUnit.MILLISECONDS.toNanos(REPRIORITY_INTERVAL_MS)) {
            gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
            repriorityTimers[address] = now
        }
    }

    private fun updateConnectionState(
        sensorId: SensorId,
        state: ConnectionState,
    ) {
        _connectionState.update { current ->
            current.toMutableMap().apply { put(sensorId, state) }
        }
    }

    // --- Inner types ---

    data class ScanResult(val name: String, val address: String, val rssi: Int)

    enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }
}
