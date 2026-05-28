package ru.skatelab.shared.utils

private const val CONFIDENCE_THRESHOLD = 0.3f

fun interpolatePose(
    poses: List<List<List<Float>>>,
    keyframeInterval: Int,
    frameIndex: Int,
): List<List<Float>?>? {
    if (poses.isEmpty()) return null

    val lastKeyframeIdx = poses.lastIndex
    val lastFrameIdx = lastKeyframeIdx * keyframeInterval

    // Past last keyframe: return last keyframe (with confidence filtering)
    if (frameIndex >= lastFrameIdx) return poses[lastKeyframeIdx].map { kp ->
        if (kp[2] < CONFIDENCE_THRESHOLD) null else kp
    }

    // Before first keyframe: return first keyframe
    if (frameIndex <= 0) return poses[0].map { kp ->
        if (kp[2] < CONFIDENCE_THRESHOLD) null else kp
    }

    val floorIdx = (frameIndex / keyframeInterval).coerceAtMost(lastKeyframeIdx - 1)
    val ceilIdx = floorIdx + 1
    val t = (frameIndex - floorIdx * keyframeInterval).toFloat() / keyframeInterval

    return poses[floorIdx].mapIndexed { i, floorKp ->
        val ceilKp = poses[ceilIdx][i]
        val conf = minOf(floorKp[2], ceilKp[2])
        if (conf < CONFIDENCE_THRESHOLD) null
        else listOf(
            floorKp[0] * (1 - t) + ceilKp[0] * t,
            floorKp[1] * (1 - t) + ceilKp[1] * t,
            conf,
        )
    }
}
