package ru.skatelab.capture.data.ble

import android.os.SystemClock
import com.juul.kable.Advertisement
import com.juul.kable.Filter
import com.juul.kable.Peripheral
import com.juul.kable.Scanner
import com.juul.kable.WriteType
import com.juul.kable.characteristicOf
import com.juul.kable.logs.Logging
import com.juul.kable.peripheral
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.domain.model.ImuSample
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.BleRepository
import ru.skatelab.capture.domain.repository.ScanDevice

/**
 * Kable-based BLE repository implementation.
 *
 * Wraps the Kable coroutine-based BLE API to match the [BleRepository] interface.
 * Uses the existing [Wt901Parser] and [Wt901Commander] for WT901 protocol handling.
 *
 * Compared to [BleRepositoryImpl] (raw Android BLE), Kable provides:
 * - Coroutine-native API (no HandlerThread needed)
 * - Automatic CCCD subscription management via [Peripheral.observe]
 * - Built-in reconnection support via state monitoring
 * - Thread-safe peripheral access
 */
@Singleton
class KableBleRepository
    @Inject
    constructor(
        private val appLogger: AppLogger,
    ) : BleRepository {
        private companion object {
            const val TAG = "KableBleRepo"
            const val SERVICE_UUID_STR = "0000FFE5-0000-1000-8000-00805F9A34FB"
            const val NOTIFY_UUID_STR = "0000FFE4-0000-1000-8000-00805F9A34FB"
            const val WRITE_UUID_STR = "0000FFE9-0000-1000-8000-00805F9A34FB"
            val SERVICE_UUID: UUID = UUID.fromString(SERVICE_UUID_STR)
            const val SET_RATE_DELAY_MS = 1000L
            const val DEFAULT_RATE = 0x09 // 100Hz
            private const val DEFAULT_RATE_HZ = 100L
            const val CONNECT_TIMEOUT_MS = 15_000L
        }

        private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

        // Per-sensor state
        private val peripherals = ConcurrentHashMap<SensorId, Peripheral>()
        private val parsers = ConcurrentHashMap<SensorId, Wt901Parser>()
        private val addressMap = ConcurrentHashMap<SensorId, String>()
        private val observationJobs = ConcurrentHashMap<SensorId, Job>()
        private val reconnectJobs = ConcurrentHashMap<SensorId, Job>()
        private val stateMonitorJobs = ConcurrentHashMap<SensorId, Job>()
        private val setRateJobs = ConcurrentHashMap<SensorId, Job>()

        // Cached advertisements from scanning (keyed by identifier/address string)
        private val cachedAdvertisements = ConcurrentHashMap<String, Advertisement>()

        // shared flows
        private val _scanResults = MutableStateFlow<List<ScanDevice>>(emptyList())
        override val scanResults: Flow<List<ScanDevice>> = _scanResults.asStateFlow()

        private val _connectionState = MutableStateFlow<Map<SensorId, BleRepository.ConnectionState>>(emptyMap())
        override val connectionState: Flow<Map<SensorId, BleRepository.ConnectionState>> =
            _connectionState.asStateFlow()

        private val _imuSamples = MutableSharedFlow<Pair<SensorId, ImuSample>>(extraBufferCapacity = 1024)
        override val imuSamples: Flow<Pair<SensorId, ImuSample>> = _imuSamples.asSharedFlow()

        private val _reconnectEvents = MutableSharedFlow<SensorId>(extraBufferCapacity = 8)
        override val reconnectEvents: Flow<SensorId> = _reconnectEvents.asSharedFlow()

        // Register read responses (for battery, firmware, etc.)
        @Suppress("ktlint:standard:property-naming")
        private val _registerReadResults = MutableSharedFlow<Pair<String, RegisterReadResult>>(extraBufferCapacity = 8)

        private var scanJob: Job? = null

        // WT901 characteristics (Kable characteristicOf uses String UUIDs)
        private val notifyCharacteristic =
            characteristicOf(
                service = SERVICE_UUID_STR,
                characteristic = NOTIFY_UUID_STR,
            )
        private val writeCharacteristic =
            characteristicOf(
                service = SERVICE_UUID_STR,
                characteristic = WRITE_UUID_STR,
            )

        private fun logi(msg: String) {
            android.util.Log.i(TAG, msg)
            appLogger.i(TAG, msg)
        }

        private fun logw(msg: String) {
            android.util.Log.w(TAG, msg)
            appLogger.w(TAG, msg)
        }

        private fun loge(msg: String) {
            android.util.Log.e(TAG, msg)
            appLogger.e(TAG, msg)
        }

        // --- Scanning ---

        override fun startScan() {
            if (scanJob?.isActive == true) return

            logi("Starting Kable BLE scan with filter $SERVICE_UUID")

            val scanner =
                Scanner {
                    filters = listOf(Filter.Service(SERVICE_UUID))
                    logging {
                        level = Logging.Level.Warnings
                    }
                }

            val foundDevices = mutableMapOf<String, ScanDevice>()

            scanJob =
                scope.launch {
                    scanner.advertisements.collect { advertisement ->
                        val name = advertisement.name ?: "WT901"
                        val address = advertisement.identifier
                        val rssi = advertisement.rssi
                        logi("Scan result: $name @ $address RSSI=$rssi")
                        // Cache advertisement for later Peripheral creation
                        cachedAdvertisements[address] = advertisement
                        foundDevices[address] = ScanDevice(name = name, address = address, rssi = rssi)
                        _scanResults.value = foundDevices.values.toList()
                    }
                }
        }

        override fun stopScan() {
            scanJob?.cancel()
            scanJob = null
            logi("BLE scan stopped")
        }

        // --- Connection ---

        override suspend fun connect(
            sensorId: SensorId,
            address: String,
        ): Result<Unit> {
            try {
                updateConnectionState(sensorId, BleRepository.ConnectionState.CONNECTING)
                addressMap[sensorId] = address

                // Create peripheral from cached advertisement or MAC address
                val peripheral = createPeripheral(sensorId, address)
                peripherals[sensorId] = peripheral

                // Monitor connection state changes
                stateMonitorJobs[sensorId]?.cancel()
                stateMonitorJobs[sensorId] =
                    scope.launch {
                        peripheral.state.collect { state ->
                            when (state) {
                                is com.juul.kable.State.Connecting -> {
                                    updateConnectionState(sensorId, BleRepository.ConnectionState.CONNECTING)
                                }
                                is com.juul.kable.State.Connected -> {
                                    logi("Sensor $sensorId connected")
                                    updateConnectionState(sensorId, BleRepository.ConnectionState.CONNECTED)
                                }
                                is com.juul.kable.State.Disconnecting -> {
                                    // No-op, transient state
                                }
                                is com.juul.kable.State.Disconnected -> {
                                    logw("Sensor $sensorId disconnected: ${state.status}")
                                    // Auto-reconnect if peripheral is still tracked
                                    if (peripherals[sensorId] != null) {
                                        updateConnectionState(sensorId, BleRepository.ConnectionState.RECONNECTING)
                                        _reconnectEvents.tryEmit(sensorId)
                                        reconnectJobs[sensorId]?.cancel()
                                        reconnectJobs[sensorId] =
                                            scope.launch {
                                                kotlinx.coroutines.delay(2000L)
                                                try {
                                                    peripheral.connect()
                                                    startObservation(sensorId)
                                                    scheduleSetRate(sensorId)
                                                    logi("Reconnected $sensorId")
                                                } catch (e: Exception) {
                                                    loge("Reconnect failed for $sensorId: ${e.message}")
                                                    updateConnectionState(sensorId, BleRepository.ConnectionState.DISCONNECTED)
                                                }
                                            }
                                    } else {
                                        updateConnectionState(sensorId, BleRepository.ConnectionState.DISCONNECTED)
                                    }
                                }
                            }
                        }
                    }

                // Connect with timeout
                val connected =
                    withTimeoutOrNull(CONNECT_TIMEOUT_MS) {
                        try {
                            peripheral.connect()
                            true
                        } catch (e: Exception) {
                            loge("Connect failed for $sensorId: ${e.message}")
                            false
                        }
                    }

                return if (connected == true) {
                    // Wait until state is CONNECTED
                    withTimeoutOrNull(5000L) {
                        _connectionState.first { it[sensorId] == BleRepository.ConnectionState.CONNECTED }
                    }
                    // Cancel pending reconnect job — connection is successful
                    reconnectJobs[sensorId]?.cancel()
                    reconnectJobs.remove(sensorId)
                    // Start observing IMU data (Kable observe automatically handles CCCD)
                    startObservation(sensorId)
                    // Send setRate after a delay (matches BleManager behavior)
                    scheduleSetRate(sensorId)
                    logi("Sensor $sensorId connected and ready")
                    Result.success(Unit)
                } else {
                    loge("Sensor $sensorId connection failed or timeout")
                    cleanupPeripheral(sensorId)
                    Result.failure(IllegalStateException("Connection failed for $sensorId"))
                }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Exception) {
                loge("Connect exception for $sensorId: ${e.message}")
                cleanupPeripheral(sensorId)
                return Result.failure(e)
            }
        }

        override suspend fun disconnect(sensorId: SensorId): Result<Unit> =
            runCatching {
                val peripheral = peripherals[sensorId]
                if (peripheral != null) {
                    observationJobs[sensorId]?.cancel()
                    observationJobs.remove(sensorId)
                    reconnectJobs[sensorId]?.cancel()
                    reconnectJobs.remove(sensorId)
                    stateMonitorJobs[sensorId]?.cancel()
                    stateMonitorJobs.remove(sensorId)
                    setRateJobs[sensorId]?.cancel()
                    setRateJobs.remove(sensorId)
                    try {
                        peripheral.disconnect()
                    } catch (_: Exception) {
                        // Best effort
                    }
                }
                cleanupPeripheral(sensorId)
            }

        // --- Sensor Commands ---

        override suspend fun factoryResetSensor(sensorId: SensorId): Result<Unit> =
            runCatching {
                writeCommand(sensorId, Wt901Commander.factoryReset())
            }

        override suspend fun accCalibrateSensor(sensorId: SensorId): Result<Unit> =
            runCatching {
                writeSequence(sensorId, Wt901Commander.bleAccCalibrateSequence())
            }

        /** No-op in BLE mode — 0x61 streams automatically when CCCD is enabled (Kable observe). */
        override suspend fun startStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        /** No-op in BLE mode — streaming stops when observation is cancelled or sensor disconnects. */
        override suspend fun stopStreaming(sensorId: SensorId): Result<Unit> = Result.success(Unit)

        override suspend fun readBattery(sensorId: SensorId): Result<Int> {
            val result = readRegisterResponse(sensorId, 0x64)
            return result.map { data -> BleRepository.rawBatteryToPercent(data[0].toInt()) }
        }

        override suspend fun readChipTime(sensorId: SensorId): Result<Long> {
            val result = readRegisterResponse(sensorId, 0x50)
            return result.map { data ->
                val low = data[0].toLong() and 0xFFFF
                val mid = data[1].toLong() and 0xFFFF
                val high = data[2].toLong() and 0xFFFF
                (high shl 32) or (mid shl 16) or low
            }
        }

        override suspend fun readDeviceId(sensorId: SensorId): Result<String> =
            runCatching {
                val data = readRegisterResponse(sensorId, 0x68).getOrThrow()
                "%04X%04X%04X".format(data[0].toInt() and 0xFFFF, data[1].toInt() and 0xFFFF, data[2].toInt() and 0xFFFF)
            }

        override suspend fun readFirmwareVersion(sensorId: SensorId): Result<String> =
            runCatching {
                val data = readRegisterResponse(sensorId, 0x60).getOrThrow()
                val major = (data[0].toInt() and 0xFFFF) shr 8
                val minor = data[0].toInt() and 0xFF
                val patch = (data[1].toInt() and 0xFF00) shr 8
                "$major.$minor.$patch"
            }

        override suspend fun readBatteryMv(sensorId: SensorId): Result<Int> =
            runCatching {
                val data = readRegisterResponse(sensorId, 0x64).getOrThrow()
                data[0].toInt() // Raw value — unit unverified
            }

        override suspend fun configureSensorTime(sensorId: SensorId): Result<Unit> =
            runCatching {
                writeSequence(sensorId, Wt901Commander.timeConfigSequence())
            }

        override fun getConnectedDevices(): List<ScanDevice> =
            peripherals.mapNotNull { (sensorId, _) ->
                val state = _connectionState.value[sensorId]
                if (state == BleRepository.ConnectionState.CONNECTED) {
                    val address = addressMap[sensorId] ?: return@mapNotNull null
                    ScanDevice(name = "WT901", address = address, rssi = 0, isConnected = true)
                } else {
                    null
                }
            }

        override fun getAddressForSensor(sensorId: SensorId): String? = addressMap[sensorId]

        // --- Private Helpers ---

        /**
         * Create a Kable Peripheral from a cached advertisement or MAC address string.
         * On Android, Kable supports creating peripherals from Advertisement objects or MAC address strings.
         */
        private fun createPeripheral(
            sensorId: SensorId,
            address: String,
        ): Peripheral {
            val advertisement = cachedAdvertisements[address]
            return if (advertisement != null) {
                logi("Creating peripheral from cached advertisement for $sensorId @ $address")
                scope.peripheral(advertisement) {
                    logging {
                        level = Logging.Level.Warnings
                    }
                }
            } else {
                // Fallback: create from MAC address string (Android-specific)
                logi("Creating peripheral from MAC address for $sensorId @ $address")
                scope.peripheral(address) {
                    logging {
                        level = Logging.Level.Warnings
                    }
                }
            }
        }

        private fun startObservation(sensorId: SensorId) {
            observationJobs[sensorId]?.cancel()
            val peripheral = peripherals[sensorId] ?: return
            val parser =
                Wt901Parser().also {
                    it.logTag = "KableWt901-${sensorId.name}"
                    it.onRegisterRead = { result ->
                        val address = addressMap[sensorId]
                        if (address != null) {
                            _registerReadResults.tryEmit(address to result)
                        }
                    }
                }
            parsers[sensorId] = parser

            observationJobs[sensorId] =
                scope.launch {
                    peripheral.observe(notifyCharacteristic)
                        .catch { e ->
                            loge("Observation error for $sensorId: ${e.message}")
                        }
                        .collect { bytes ->
                            val arrivalNs = SystemClock.elapsedRealtimeNanos()
                            val samples = parser.feed(bytes, arrivalNs)
                            // WT901 notifications may batch several 100 Hz frames.
                            // Parser arrival time is identical for the batch, so spread
                            // samples over the nominal period before persisting them.
                            val periodNs = 1_000_000_000L / DEFAULT_RATE_HZ
                            samples.mapIndexed { index, sample ->
                                sample.copy(
                                    timestampNs = arrivalNs - (samples.size - 1 - index) * periodNs,
                                )
                            }.forEach { sample ->
                                _imuSamples.tryEmit(sensorId to sample)
                            }
                        }
                }
        }

        private fun scheduleSetRate(sensorId: SensorId) {
            setRateJobs[sensorId]?.cancel()
            setRateJobs[sensorId] =
                scope.launch {
                    kotlinx.coroutines.delay(SET_RATE_DELAY_MS)
                    try {
                        writeCommand(sensorId, Wt901Commander.setRate(DEFAULT_RATE))
                        logi("setRate(0x09) sent to $sensorId")
                    } catch (e: Exception) {
                        loge("setRate failed for $sensorId: ${e.message}")
                    }
                }
        }

        private suspend fun writeCommand(
            sensorId: SensorId,
            bytes: ByteArray,
        ) {
            val peripheral = peripherals[sensorId] ?: throw IllegalStateException("No peripheral for $sensorId")
            peripheral.write(writeCharacteristic, bytes, WriteType.WithoutResponse)
        }

        private suspend fun writeSequence(
            sensorId: SensorId,
            steps: List<Wt901Commander.CommandStep>,
        ) {
            logi("writeSequence: $sensorId steps=${steps.size}")
            kotlinx.coroutines.delay(100L)
            for ((index, step) in steps.withIndex()) {
                writeCommand(sensorId, step.bytes)
                kotlinx.coroutines.delay(maxOf(step.delayAfterMs, 30L))
                logi("writeSequence step $index/${steps.size} sent")
            }
            logi("writeSequence complete: $sensorId")
        }

        private suspend fun readRegisterResponse(
            sensorId: SensorId,
            register: Int,
            timeoutMs: Long = 2000L,
        ): Result<ShortArray> {
            val address = addressMap[sensorId] ?: return Result.failure(IllegalArgumentException("No address for $sensorId"))
            writeCommand(sensorId, Wt901Commander.readRegister(register))

            return try {
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

        private fun cleanupPeripheral(sensorId: SensorId) {
            observationJobs.remove(sensorId)?.cancel()
            reconnectJobs.remove(sensorId)?.cancel()
            stateMonitorJobs.remove(sensorId)?.cancel()
            setRateJobs.remove(sensorId)?.cancel()
            parsers.remove(sensorId)
            peripherals.remove(sensorId)
            addressMap.remove(sensorId)
            updateConnectionState(sensorId, BleRepository.ConnectionState.DISCONNECTED)
        }

        private fun updateConnectionState(
            sensorId: SensorId,
            state: BleRepository.ConnectionState,
        ) {
            _connectionState.update { current ->
                current.toMutableMap().apply { put(sensorId, state) }
            }
        }
    }
