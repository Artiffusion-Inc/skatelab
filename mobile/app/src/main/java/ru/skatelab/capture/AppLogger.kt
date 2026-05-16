package ru.skatelab.capture

import android.content.Context
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentLinkedQueue
import javax.inject.Inject
import javax.inject.Singleton
import ru.skatelab.capture.domain.service.Logger

@Singleton
class AppLogger
    @Inject
    constructor(
        @ApplicationContext context: Context,
    ) : Logger {
        private val logFile: File = File(context.filesDir, "app.log")
        private var writer: FileWriter? = null
        private val dateFormat = SimpleDateFormat("HH:mm:ss.SSS", Locale.US)
        private val queue = ConcurrentLinkedQueue<String>()
        private val flushRunnable =
            object : Runnable {
                override fun run() {
                    flush()
                    if (writer != null) {
                        handler?.postDelayed(this, 500)
                    }
                }
            }
        private var handler: android.os.Handler? = null

        fun open() {
            try {
                logFile.parentFile?.mkdirs()
                writer = FileWriter(logFile, true)
                handler = android.os.Handler(android.os.Looper.getMainLooper())
                writeLine("=== APP LOG OPENED ===")
                handler?.postDelayed(flushRunnable, 500)
            } catch (e: Exception) {
                android.util.Log.e("AppLogger", "open failed: ${e.message}")
            }
        }

        fun close() {
            try {
                writeLine("=== APP LOG CLOSED ===")
                flush()
                handler?.removeCallbacks(flushRunnable)
                writer?.close()
            } catch (_: Exception) {
            }
            writer = null
            handler = null
        }

        override fun i(
            tag: String,
            msg: String,
        ) {
            Log.i(tag, msg)
            queue.add("I/$tag: $msg")
        }

        override fun d(
            tag: String,
            msg: String,
        ) {
            Log.d(tag, msg)
            queue.add("D/$tag: $msg")
        }

        override fun w(
            tag: String,
            msg: String,
        ) {
            Log.w(tag, msg)
            queue.add("W/$tag: $msg")
        }

        override fun e(
            tag: String,
            msg: String,
        ) {
            Log.e(tag, msg)
            queue.add("E/$tag: $msg")
        }

        private fun writeLine(line: String) {
            try {
                val ts = dateFormat.format(Date())
                writer?.append("[$ts] $line\n")
            } catch (_: Exception) {
            }
        }

        private fun flush() {
            try {
                while (true) {
                    val line = queue.poll() ?: break
                    val ts = dateFormat.format(Date())
                    writer?.append("[$ts] $line\n")
                }
                writer?.flush()
            } catch (_: Exception) {
            }
        }

        fun getLogContent(): String {
            flush()
            return try {
                logFile.readText()
            } catch (_: Exception) {
                ""
            }
        }

        fun clear() {
            try {
                close()
                logFile.delete()
                open()
            } catch (_: Exception) {
            }
        }
    }
