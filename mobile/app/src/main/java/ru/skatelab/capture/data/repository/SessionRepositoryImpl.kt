package ru.skatelab.capture.data.repository

import android.content.Context
import ru.skatelab.capture.AppLogger
import dagger.hilt.android.qualifiers.ApplicationContext
import org.json.JSONObject
import ru.skatelab.capture.domain.model.CalibrationData
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.repository.SessionRepository
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SessionRepositoryImpl @Inject constructor(
    @ApplicationContext private val context: Context,
    private val appLogger: AppLogger,
) : SessionRepository {

    companion object {
        private const val TAG = "SessionRepo"
        private const val SESSIONS_DIR = "sessions"
        private const val META_FILE = "meta.json"
    }

    private val sessionsDir: File
        get() = File(context.filesDir, SESSIONS_DIR)

    override suspend fun saveSession(session: CaptureSession): Result<Unit> = runCatching {
        val dir = File(sessionsDir, session.id)
        dir.mkdirs()
        val metaFile = File(dir, META_FILE)
        metaFile.writeText(sessionToJson(session))
        appLogger.i(TAG, "Session saved: ${session.id}")
    }

    override suspend fun getSessions(): List<CaptureSession> {
        if (!sessionsDir.exists()) return emptyList()
        return sessionsDir.listFiles()
            ?.filter { it.isDirectory }
            ?.mapNotNull { dir ->
                val metaFile = File(dir, META_FILE)
                if (metaFile.exists()) jsonToSession(metaFile.readText(), dir) else null
            }
            ?: emptyList()
    }

    override suspend fun getSession(id: String): CaptureSession? {
        val dir = File(sessionsDir, id)
        val metaFile = File(dir, META_FILE)
        if (!metaFile.exists()) return null
        return jsonToSession(metaFile.readText(), dir)
    }

    override suspend fun deleteSession(id: String): Result<Unit> = runCatching {
        val dir = File(sessionsDir, id)
        if (dir.exists()) dir.deleteRecursively()
    }

    private fun sessionToJson(s: CaptureSession): String {
        val imuDelayEntries = s.imuStartDelayMs.entries.joinToString(",") { (k, v) ->
            "\"${k.name}\": $v"
        }
        val calEntries = s.calibration.entries.joinToString(",") { (sensorId, cal) ->
            "\"${sensorId.name}\": {\"quatRef\": [${cal.quatRef.joinToString(",")}],\"calibratedAt\": ${cal.calibratedAt}}"
        }
        val clockOffsetEntries = s.clockOffsetNs.entries.joinToString(",") { (k, v) ->
            "\"${k.name}\": $v"
        }
        return buildString {
            appendLine("{")
            appendLine("  \"id\": \"${s.id}\",")
            appendLine("  \"videoPath\": \"${s.videoFile.absolutePath}\",")
            appendLine("  \"imuLeftPath\": \"${s.imuLeftFile.absolutePath}\",")
            appendLine("  \"imuRightPath\": \"${s.imuRightFile.absolutePath}\",")
            appendLine("  \"frameTimestampsPath\": \"${s.frameTimestampsFile.absolutePath}\",")
            appendLine("  \"manifestPath\": \"${s.manifestFile.absolutePath}\",")
            appendLine("  \"t0Ns\": ${s.t0Ns},")
            appendLine("  \"durationMs\": ${s.durationMs},")
            appendLine("  \"videoFps\": ${s.videoFps},")
            appendLine("  \"timestampSource\": \"${s.timestampSource}\",")
            appendLine("  \"videoStartDelayMs\": ${s.videoStartDelayMs},")
            appendLine("  \"imuStartDelayMs\": {$imuDelayEntries},")
            appendLine("  \"calibration\": {$calEntries},")
            appendLine("  \"clockOffsetNs\": {$clockOffsetEntries},")
            appendLine("  \"createdAt\": ${s.createdAt},")
            appendLine("  \"isComplete\": ${s.isComplete}")
            append("}")
        }
    }

    private fun jsonToSession(json: String, dir: File): CaptureSession? {
        return try {
            val o = JSONObject(json)
            val imuStartDelayMs = o.optJSONObject("imuStartDelayMs")?.let { obj ->
                SensorId.entries.mapNotNull { id ->
                    obj.optLong(id.name, -1L).takeIf { it >= 0 }?.let { id to it }
                }.toMap()
            } ?: emptyMap()

            val calibration = o.optJSONObject("calibration")?.let { obj ->
                SensorId.entries.mapNotNull { id ->
                    obj.optJSONObject(id.name)?.let { calObj ->
                        val quatArr = calObj.optJSONArray("quatRef")?.let { arr ->
                            FloatArray(arr.length()) { arr.getDouble(it).toFloat() }
                        } ?: FloatArray(4)
                        id to CalibrationData(
                            quatRef = quatArr,
                            calibratedAt = calObj.optLong("calibratedAt", 0L),
                        )
                    }
                }.toMap()
            } ?: emptyMap()

            val clockOffsetNs = o.optJSONObject("clockOffsetNs")?.let { obj ->
                SensorId.entries.mapNotNull { id ->
                    obj.optLong(id.name, Long.MIN_VALUE).takeIf { it != Long.MIN_VALUE }?.let { id to it }
                }.toMap()
            } ?: emptyMap()

            CaptureSession(
                id = o.getString("id"),
                videoFile = File(o.getString("videoPath")),
                imuLeftFile = File(o.getString("imuLeftPath")),
                imuRightFile = File(o.getString("imuRightPath")),
                frameTimestampsFile = File(o.getString("frameTimestampsPath")),
                manifestFile = File(o.getString("manifestPath")),
                t0Ns = o.getLong("t0Ns"),
                durationMs = o.getLong("durationMs"),
                videoFps = o.getInt("videoFps"),
                timestampSource = o.optString("timestampSource", "unknown"),
                videoStartDelayMs = o.optLong("videoStartDelayMs", 0),
                imuStartDelayMs = imuStartDelayMs,
                calibration = calibration,
                clockOffsetNs = clockOffsetNs,
                createdAt = o.getLong("createdAt"),
                isComplete = o.optBoolean("isComplete", false),
            )
        } catch (e: Exception) {
            appLogger.e(TAG, "Failed to parse session from $dir: ${e.message}")
            null
        }
    }
}
