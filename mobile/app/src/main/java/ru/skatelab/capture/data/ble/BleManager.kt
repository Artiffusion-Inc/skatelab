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
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import java.util.UUID
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

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

    // Per-sensor handler threads — eliminates head-of-line blocking between sensors
    private val handlerThreads = ConcurrentHashMap<String, BleHandlerThread>()

    // Active GATT connections keyed by sensor address
    private val gattConnections = ConcurrentHashMap<String, BluetoothGatt>()
    private val writeCharacteristics = ConcurrentHashMap<String, BluetoothGattCharacteristic>()
    private val notifyCharacteristics = ConcurrentHashMap<String, BluetoothGattCharacteristic>()

    // Flows for scan results, connection state, and IMU samples
    private val _scanResults = MutableStateFlow<List<ScanResult>>(emptyList())
    val scanResults: Flow<List<ScanResult>> = _scanResults.asStateFlow()

    private val _connectionState = MutableStateFlow<Map<SensorId, ConnectionState>>(emptyMap())
    val connectionState: Flow<Map<SensorId, ConnectionState>> = _connectionState.asStateFlow()

    private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 1024)
    val imuSamples: Flow<Pair<SensorId, ImuSample>> = _imuSamples.asSharedFlow()

    // Register read responses: (sensorAddress, RegisterReadResult)
    private val _registerReadResults = MutableSharedFlow<Pair<String, RegisterReadResult>>(extraBufferCapacity = 8)
    val registerReadResults: Flow<Pair<String, RegisterReadResult>> = _registerReadResults.asSharedFlow()

    private val _reconnectEvents = MutableSharedFlow<SensorId>(extraBufferCapacity = 8)
    val reconnectEvents: Flow<SensorId> = _reconnectEvents.asSharedFlow()

    /** Per-sensor recording state. Set by BleRepositoryImpl. */
    private val recordingSensors: MutableSet<SensorId> = ConcurrentHashMap.newKeySet()

    /** Tracks addresses of sensors explicitly disconnected by user (vs auto-disconnect). */
    private val explicitlyDisconnected: MutableSet<String> = ConcurrentHashMap.newKeySet()

    fun markRecording(sensorId: SensorId) { recordingSensors.add(sensorId) }
    fun markStopped(sensorId: SensorId) { recordingSensors.remove(sensorId) }
    fun isRecording(sensorId: SensorId): Boolean = sensorId in recordingSensors

    @Volatile
    private var activeScanCallback: android.bluetooth.le.ScanCallback? = null

    // Map sensor address to SensorId (assigned by user during scan)
    private val addressToSensorId = ConcurrentHashMap<String, SensorId>()

    // Re-priority timer per sensor
    private val repriorityTimers = ConcurrentHashMap<String, Long>()

    // Per-sensor Mutex — prevents concurrent sendSequence from interleaving commands
    private val sensorMutexes = ConcurrentHashMap<String, Mutex>()

    // GATT write queue per sensor — serializes write operations
    private val writeQueues = ConcurrentHashMap<String, MutableList<GattWriteEntry>>()
    private val writeInProgress = ConcurrentHashMap<String, Boolean>()

    // --- Scanning ---

    @SuppressLint("MissingPermission")
    fun startScan() {
        val adapter = bluetoothAdapter ?: run { loge("No BluetoothAdapter"); return }
        val scanner = adapter.bluetoothLeScanner ?: run { loge("No BLE scanner"); return }
        logi("Starting BLE scan with filter $SERVICE_UUID")

        // Clear previous results so UI shows fresh scan
        _scanResults.value = emptyList()

        val filter = android.bluetooth.le.ScanFilter.Builder()
            .setServiceUuid(android.os.ParcelUuid.fromString(SERVICE_UUID.toString()))
            .build()

        val settings = android.bluetooth.le.ScanSettings.Builder()
            .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        val foundDevices = Collections.synchronizedMap(mutableMapOf<String, ScanResult>())

        val callback = object : android.bluetooth.le.ScanCallback() {
            override fun onScanResult(callbackType: Int, result: android.bluetooth.le.ScanResult) {
                try {
                    val device = result.device
                    logi("Scan result: ${device.name} @ ${device.address} RSSI=${result.rssi}")
                    val name = device.name ?: "WT901"
                    val address = device.address
                    foundDevices[address] = ScanResult(name, address, result.rssi)
                    _scanResults.value = foundDevices.values.toList()
                } catch (e: Exception) {
                    loge("ScanCallback onScanResult error: ${e.message}")
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

    // --- Connection ---

    @SuppressLint("MissingPermission")
    suspend fun connect(sensorId: SensorId, address: String): Result<Unit> {
        val adapter = bluetoothAdapter ?: return Result.failure(IllegalStateException("No BluetoothAdapter"))
        val device = adapter.getRemoteDevice(address) ?: return Result.failure(IllegalArgumentException("Device not found: $address"))

        addressToSensorId[address] = sensorId
        // Clear any stale explicit-disconnect flag from a previous session
        explicitlyDisconnected.remove(address)
        updateConnectionState(sensorId, ConnectionState.CONNECTING)

        // Create per-sensor handler thread to avoid head-of-line blocking
        val ht = BleHandlerThread("ble-parse-${sensorId.name.lowercase()}")
        ht.start()
        ht.prepareHandler()
        ht.setRegisterReadCallback { addr, result ->
            _registerReadResults.tryEmit(addr to result)
        }
        handlerThreads[address] = ht

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
            // Close leaked GATT object on connect timeout to prevent system-wide GATT exhaustion
            gattConnections.remove(address)?.close()
            handlerThreads.remove(address)?.quitSafely()
            addressToSensorId.remove(address)
            updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
            Result.failure(IllegalStateException("Connection failed for $sensorId, state=$state"))
        }
    }

    @SuppressLint("MissingPermission")
    fun disconnect(sensorId: SensorId, address: String) {
        // Mark as explicitly disconnected to prevent auto-reconnect
        explicitlyDisconnected.add(address)
        // Remove pending reconnect messages on the handler thread
        handlerThreads[address]?.handler?.removeCallbacksAndMessages(null)
        val gatt = gattConnections.remove(address) ?: return
        writeCharacteristics.remove(address)
        notifyCharacteristics.remove(address)
        handlerThreads.remove(address)?.quitSafely()
        addressToSensorId.remove(address)
        repriorityTimers.remove(address)
        recordingSensors.remove(sensorId)
        gatt.disconnect()
        gatt.close()
        updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
    }

    // --- GATT Callback ---

    @SuppressLint("MissingPermission")
    private fun createGattCallback(sensorId: SensorId, address: String): BluetoothGattCallback = object : BluetoothGattCallback() {

        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            logi("GATT state change: address=$address status=$status newState=$newState")

            // GATT error 133 means the stack is in a bad state — close the GATT object
            // before attempting any new connection, otherwise connectGatt() loops forever.
            if (status == 133 && newState == BluetoothProfile.STATE_DISCONNECTED) {
                logw("GATT error 133 for $address — closing stale GATT object")
                gattConnections.remove(address)
                gatt.close()
                updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                return
            }

            if (newState == BluetoothProfile.STATE_CONNECTED) {
                gattConnections[address] = gatt
                // Route GATT setup through HandlerThread for consistent threading
                handlerThreads[address]?.handler?.post {
                    gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                    gatt.requestMtu(247)
                } ?: run {
                    // Fallback: call directly if handler not available
                    gatt.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_HIGH)
                    gatt.requestMtu(247)
                }
            } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                // Always close the old GATT object to prevent leaks
                // (Android has a ~30 GATT limit system-wide before refusing new connections)
                gattConnections.remove(address)
                gatt.close()

                // Skip reconnect if user explicitly disconnected
                if (address in explicitlyDisconnected) {
                    explicitlyDisconnected.remove(address)
                    updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                    return
                }

                // Auto-reconnect if sensor was previously connected (not explicit disconnect)
                if (isRecording(sensorId)) {
                    logw("BLE disconnected during recording, attempting reconnect: $address")
                    updateConnectionState(sensorId, ConnectionState.RECONNECTING)
                    _reconnectEvents.tryEmit(sensorId)
                    // Delayed reconnect on per-sensor handler thread
                    handlerThreads[address]?.handler?.postDelayed({
                        // Double-check: user may have disconnected during the delay
                        if (address in explicitlyDisconnected) {
                            explicitlyDisconnected.remove(address)
                            updateConnectionState(sensorId, ConnectionState.DISCONNECTED)
                            return@postDelayed
                        }
                        try {
                            val device: BluetoothDevice = gatt.device
                            val callback: BluetoothGattCallback = createGattCallback(sensorId, address)
                            device.connectGatt(context, false, callback)
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

        override fun onMtuChanged(gatt: BluetoothGatt, mtu: Int, status: Int) {
            logi("MTU changed: address=$address mtu=$mtu status=$status")
            // Route discoverServices through HandlerThread for consistent GATT threading
            handlerThreads[address]?.handler?.post {
                gatt.discoverServices()
            } ?: gatt.discoverServices()
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

            // Offload parsing to per-sensor handler thread (arrivalNs captured on Binder thread)
            handlerThreads[address]?.postParsing(bytes, address, arrivalNs) { sample ->
                if (sample != null) {
                    val id = addressToSensorId[address]
                    if (id == null) {
                        logw("postParsing: no SensorId for address=$address, available=${addressToSensorId.keys}")
                        return@postParsing
                    }
                    val emitted = _imuSamples.tryEmit(id to sample)
                    if (!emitted) {
                        logw("tryEmit DROPPED sample for $id — SharedFlow buffer full")
                    }
                }
            }
        }

        override fun onCharacteristicWrite(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic, status: Int) {
            // WRITE_TYPE_NO_RESPONSE may not trigger this callback on some devices.
            // When it does fire, drain the next queued write.
            logi("onCharacteristicWrite: $address status=$status")
            synchronized(writeQueues.getOrPut(address) { mutableListOf() }) {
                if (this@BleManager.writeQueues[address]?.isNotEmpty() == true) {
                    this@BleManager.writeQueues[address]?.removeAt(0)?.deferred?.complete(status == BluetoothGatt.GATT_SUCCESS)
                }
            }
            // Post drain to handler thread to avoid recursive Binder thread calls
            handlerThreads[address]?.handler?.postDelayed({ drainWriteQueue(address) }, 10L)
        }

        override fun onDescriptorWrite(gatt: BluetoothGatt, descriptor: BluetoothGattDescriptor, status: Int) {
            logi("onDescriptorWrite: $address uuid=${descriptor.uuid} status=$status")
            if (descriptor.uuid.toString().startsWith("00002902")) {
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    completeSetup(gatt, address, sensorId)
                } else {
                    loge("CCCD descriptor write failed (status=$status) for $address — notifications may not work")
                    gatt.disconnect()
                }
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun completeSetup(gatt: BluetoothGatt, address: String, sensorId: SensorId) {
        updateConnectionState(sensorId, ConnectionState.CONNECTED)
        logi("Sensor $sensorId CONNECTED, notify+write chars ready")
    }

    // --- Command Sending ---

    /**
     * Send a register read command and wait for the 0x71 response.
     *
     * Sends [Wt901Commander.readRegister], then suspends until a 0x71 frame
     * with the matching register address arrives or [timeoutMs] elapses.
     */
    suspend fun readRegisterResponse(
        sensorId: SensorId,
        register: Int,
        timeoutMs: Long = 2000L,
    ): Result<ShortArray> {
        val address = addressToSensorId.entries.find { it.value == sensorId }?.key
            ?: return Result.failure(IllegalArgumentException("No address for $sensorId"))

        // Acquire per-sensor Mutex to prevent interleaving with sendSequence
        val mutex = sensorMutexes.getOrPut(address) { Mutex() }
        mutex.withLock {
            sendCommand(sensorId, Wt901Commander.readRegister(register))
        }

        return try {
            val result = withTimeoutOrNull(timeoutMs) {
                _registerReadResults.first { (addr, r) ->
                    addr == address && r.register == register
                }.second
            }
            if (result != null) {
                logi("readRegisterResponse: reg=0x${register.toString(16)} data=${result.data.toList()}")
                Result.success(result.data)
            } else {
                logw("readRegisterResponse: timeout waiting for reg=0x${register.toString(16)}")
                Result.failure(java.util.concurrent.TimeoutException("No 0x71 response for register 0x${register.toString(16)} within ${timeoutMs}ms"))
            }
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            loge("readRegisterResponse: error waiting for reg=0x${register.toString(16)}: ${e.message}")
            Result.failure(e)
        }
    }

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

        // GATT write must be serialized — queue the write and drain via HandlerThread
        val queue = writeQueues.getOrPut(address) { mutableListOf() }
        synchronized(queue) {
            queue.add(GattWriteEntry(bytes, char, gatt))
            if (writeInProgress[address] != true) {
                writeInProgress[address] = true
                // Route drainWriteQueue through HandlerThread for consistent GATT thread
                handlerThreads[address]?.handler?.post { drainWriteQueue(address) }
                    ?: drainWriteQueue(address) // fallback if handler gone
            }
        }
    }

    @SuppressLint("MissingPermission")
    private fun drainWriteQueue(address: String) {
        val queue = writeQueues[address] ?: return
        val entry: GattWriteEntry
        synchronized(queue) {
            if (queue.isEmpty()) {
                writeInProgress[address] = false
                return
            }
            entry = queue.removeAt(0)
        }
        entry.char.value = entry.bytes
        val success = entry.gatt.writeCharacteristic(entry.char)
        if (!success) {
            loge("writeCharacteristic failed immediately for $address")
            // Re-queue for retry
            synchronized(queue) { queue.add(0, entry) }
            handlerThreads[address]?.handler?.postDelayed({ drainWriteQueue(address) }, 50L)
        }
        logi("writeCharacteristic $address: ${entry.bytes.joinToString("") { "%02x".format(it) }} success=$success")
    }


    /**
     * Send a sequence of command steps with inter-command delays.
     * Uses delay() between writes because WT901 uses WRITE_TYPE_NO_RESPONSE —
     * Android does NOT call onCharacteristicWrite for write-without-response,
     * so CompletableDeferred.await() would hang forever.
     * Each step's delayAfterMs provides sufficient time for the sensor to process.
     *
     * Per-sensor Mutex prevents concurrent sendSequence calls (e.g. configure + startStreaming)
     * from interleaving commands on the same sensor.
     *
     * All writeCharacteristic calls are routed through the HandlerThread to ensure
     * consistent GATT threading (Android requirement).
     */
    suspend fun sendSequence(sensorId: SensorId, steps: List<Wt901Commander.CommandStep>) {
        val address = addressToSensorId.entries.find { it.value == sensorId }?.key ?: run {
            logw("sendSequence: no address for $sensorId"); return
        }
        val mutex = sensorMutexes.getOrPut(address) { Mutex() }
        mutex.withLock {
            logi("sendSequence: $sensorId steps=${steps.size}")
            kotlinx.coroutines.delay(100L)
            for ((index, step) in steps.withIndex()) {
                val char = writeCharacteristics[address]
                val gatt = gattConnections[address]
                if (char == null || gatt == null) {
                    logw("sendSequence: missing char or gatt for $address at step $index"); continue
                }
                val queue = writeQueues.getOrPut(address) { mutableListOf() }
                synchronized(queue) {
                    queue.add(GattWriteEntry(step.bytes, char, gatt))
                    if (writeInProgress[address] != true) {
                        writeInProgress[address] = true
                        // Route drainWriteQueue through HandlerThread for consistent GATT thread
                        handlerThreads[address]?.handler?.post { drainWriteQueue(address) }
                            ?: drainWriteQueue(address) // fallback if handler gone
                    }
                }
                val minGapMs = 30L
                kotlinx.coroutines.delay(maxOf(step.delayAfterMs, minGapMs))
                logi("sendSequence step $index/${steps.size} sent: ${step.bytes.joinToString("") { "%02x".format(it) }}")
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
        _connectionState.update { current ->
            current.toMutableMap().apply { put(sensorId, state) }
        }
    }

    // --- Inner types ---

    private data class GattWriteEntry(
        val bytes: ByteArray,
        val char: BluetoothGattCharacteristic,
        val gatt: BluetoothGatt,
        val deferred: CompletableDeferred<Boolean>? = null,
    )

    data class ScanResult(val name: String, val address: String, val rssi: Int)

    enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }
}
