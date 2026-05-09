package ru.skatelab.capture.data.ble

import android.os.Handler
import android.os.HandlerThread
import android.os.SystemClock
import ru.skatelab.capture.domain.model.ImuSample

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
    private val parsers = mutableMapOf<String, Wt901Parser>()

    /**
     * Call after [start()] to prepare the [Handler] for this looper.
     */
    fun prepareHandler() {
        handler = Handler(looper)
    }

    /**
     * Get an existing parser for the given sensor, or create a new one.
     * Thread-safe: called from the handler thread itself during parsing.
     */
    fun getOrCreateParser(sensorAddress: String): Wt901Parser {
        return parsers.getOrPut(sensorAddress) { Wt901Parser() }
    }

    /**
     * Post a parsing task to the handler thread.
     *
     * @param bytes Raw BLE notification bytes (already copied).
     * @param sensorAddress MAC address of the sensor.
     * @param callback Invoked on the handler thread with the parsed sample, if any.
     */
    fun postParsing(bytes: ByteArray, sensorAddress: String, callback: (ImuSample?) -> Unit) {
        handler?.post {
            val arrivalNs = SystemClock.elapsedRealtimeNanos()
            val parser = getOrCreateParser(sensorAddress)
            val sample = parser.feed(bytes, arrivalNs)
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
