package ru.skatelab.capture.data.ble

import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import ru.skatelab.capture.domain.model.ImuSample
import java.util.concurrent.ConcurrentHashMap

/**
 * Dedicated [HandlerThread] for BLE processing.
 *
 * Android BLE callbacks arrive on Binder threads with batch behavior.
 * This handler thread offloads parsing work to avoid blocking the Binder thread.
 *
 * Usage in onCharacteristicChanged():
 *   val bytes = characteristic.value.copyOf()  // IMMEDIATE copy
 *   val arrivalNs = SystemClock.elapsedRealtimeNanos()
 *   handlerThread.postParsing(bytes, sensorAddress, callback)
 */
class BleHandlerThread(name: String = "ble-parsing") : HandlerThread(name) {

    var handler: Handler? = null
        private set
    private val parsers = ConcurrentHashMap<String, Wt901Parser>()
    private var parseCount = 0L

    // Register read callback — set by BleManager, invoked on handler thread
    private var registerReadCallback: ((String, RegisterReadResult) -> Unit)? = null

    /**
     * Call after [start()] to prepare the [Handler] for this looper.
     */
    fun prepareHandler() {
        handler = Handler(looper)
    }

    /**
     * Set the callback for register read results.
     * Called on the handler thread when a 0x71 frame is parsed.
     * @param callback (sensorAddress, RegisterReadResult) -> Unit
     */
    fun setRegisterReadCallback(callback: (String, RegisterReadResult) -> Unit) {
        registerReadCallback = callback
    }

    /**
     * Get an existing parser for the given sensor, or create a new one.
     * Thread-safe: called from the handler thread itself during parsing.
     * Wires up the [onRegisterRead] callback when a new parser is created.
     */
    fun getOrCreateParser(sensorAddress: String): Wt901Parser {
        return parsers.getOrPut(sensorAddress) {
            Wt901Parser().also { parser ->
                parser.logTag = "Wt901Parse-${sensorAddress.takeLast(5)}"
                parser.onRegisterRead = { result ->
                    registerReadCallback?.invoke(sensorAddress, result)
                }
            }
        }
    }

    /**
     * Post a parsing task to the handler thread.
     *
     * @param bytes Raw BLE notification bytes (already copied).
     * @param sensorAddress MAC address of the sensor.
     * @param arrivalNs Monotonic timestamp captured in onCharacteristicChanged.
     *   Must be captured immediately on the Binder thread — NOT inside the handler post,
     *   or batched notifications get out-of-order timestamps.
     * @param callback Invoked on the handler thread with the parsed sample, if any.
     */
    fun postParsing(bytes: ByteArray, sensorAddress: String, arrivalNs: Long, callback: (ImuSample?) -> Unit) {
        handler?.post {
            val parser = getOrCreateParser(sensorAddress)
            val sample = parser.feed(bytes, arrivalNs)
            parseCount++
            if (parseCount % 500 == 0L) {
                val accInfo = if (sample != null) "acc=[${sample.accX},${sample.accY},${sample.accZ}]" else "null"
                android.util.Log.i("BleParse", "Parsed $parseCount packets from $sensorAddress, last sample: ${sample != null}, $accInfo, dropped: ${parser.droppedPartialCount}")
            }
            callback(sample)
        }
    }

    /**
     * Remove the parser for a disconnected sensor.
     */
    fun removeParser(sensorAddress: String) {
        parsers.remove(sensorAddress)
    }
}
