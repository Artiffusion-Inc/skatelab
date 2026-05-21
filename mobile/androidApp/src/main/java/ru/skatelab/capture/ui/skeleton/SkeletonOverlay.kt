package ru.skatelab.capture.ui.skeleton

import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.dp

/**
 * A single keypoint in normalized [0, 1] coordinates.
 * [confidence] is in [0, 1]; points below [confidenceThreshold] are skipped.
 */
data class Keypoint(
    val x: Float,
    val y: Float,
    val confidence: Float = 1f,
)

/**
 * H3.6M 17-keypoint skeleton connections (start index, end index).
 * Matches the web skeleton-canvas.tsx definition exactly.
 */
val H36M_CONNECTIONS = listOf(
    // Right leg
    0 to 1,  // hip_center -> r_hip
    1 to 2,  // r_hip -> r_knee
    2 to 3,  // r_knee -> r_foot
    // Left leg
    0 to 4,  // hip_center -> l_hip
    4 to 5,  // l_hip -> l_knee
    5 to 6,  // l_knee -> l_foot
    // Spine + head
    0 to 7,  // hip_center -> spine
    7 to 8,  // spine -> thorax
    8 to 9,  // thorax -> neck
    9 to 10, // neck -> head_top
    // Left arm
    9 to 11,  // neck -> l_shoulder
    11 to 12, // l_shoulder -> l_elbow
    12 to 13, // l_elbow -> l_wrist
    // Right arm
    9 to 14,  // neck -> r_shoulder
    14 to 15, // r_shoulder -> r_elbow
    15 to 16, // r_elbow -> r_wrist
)

/**
 * Joint colors matching web skeleton-canvas.tsx JOINT_COLORS.
 * Indexed by H3.6M keypoint index (0..16).
 */
val H36M_JOINT_COLORS = listOf(
    Color.Red,                                    // 0: hip_center (red)
    Color(0f, 1f, 0f),                           // 1: r_hip (green)
    Color(0f, 1f, 0f),                           // 2: r_knee
    Color(0f, 1f, 0f),                           // 3: r_foot
    Color(0f, 0f, 1f),                           // 4: l_hip (blue)
    Color(0f, 0f, 1f),                           // 5: l_knee
    Color(0f, 0f, 1f),                           // 6: l_foot
    Color.Yellow,                                 // 7: spine (yellow)
    Color.Yellow,                                 // 8: thorax
    Color.Magenta,                                // 9: neck (magenta)
    Color.Magenta,                                // 10: head_top
    Color.Cyan,                                   // 11: l_shoulder (cyan)
    Color.Cyan,                                   // 12: l_elbow
    Color.Cyan,                                   // 13: l_wrist
    Color(red = 1f, green = 0.647f, blue = 0f),  // 14: r_shoulder (orange)
    Color(red = 1f, green = 0.647f, blue = 0f),  // 15: r_elbow
    Color(red = 1f, green = 0.647f, blue = 0f),  // 16: r_wrist
)

/** Line color for skeleton bones. */
private val BONE_COLOR = Color.White.copy(alpha = 0.6f)

/** Minimum confidence to draw a joint or bone. */
private const val DEFAULT_CONFIDENCE_THRESHOLD = 0.3f

/** Joint circle radius in dp. */
private val JOINT_RADIUS_DP = 4.dp

/** Center-of-mass dot radius in dp. */
private val COM_RADIUS_DP = 6.dp

/** Bone line width in dp. */
private val BONE_WIDTH_DP = 2.dp

/** CoM outline width in dp. */
private val COM_OUTLINE_DP = 1.dp

/**
 * A Compose [Canvas] composable that draws an H3.6M skeleton overlay.
 *
 * Designed to sit on top of an ExoPlayer video via a [Box] with matching size.
 * Keypoints use normalized [0, 1] coordinates — the composable maps them
 * to pixel offsets based on its own measured width/height.
 *
 * @param keypoints 17 H3.6M keypoints for the current frame (null = not available).
 * @param modifier Standard modifier (fillMaxSize, matchParent, etc.).
 * @param confidenceThreshold Discard keypoints below this confidence.
 * @param showCenterOfMass Draw a weighted CoM dot at pelvis/spine/neck/head.
 */
@Composable
fun SkeletonOverlay(
    keypoints: List<Keypoint?>?,
    modifier: Modifier = Modifier,
    confidenceThreshold: Float = DEFAULT_CONFIDENCE_THRESHOLD,
    showCenterOfMass: Boolean = true,
) {
    val density = LocalDensity.current
    val jointRadiusPx = with(density) { JOINT_RADIUS_DP.toPx() }
    val comRadiusPx = with(density) { COM_RADIUS_DP.toPx() }
    val boneWidthPx = with(density) { BONE_WIDTH_DP.toPx() }
    val comOutlinePx = with(density) { COM_OUTLINE_DP.toPx() }

    Canvas(modifier = modifier) {
        if (keypoints == null) return@Canvas
        if (keypoints.size < 17) return@Canvas

        val w = size.width
        val h = size.height

        // ── Draw skeleton bones ──
        for ((start, end) in H36M_CONNECTIONS) {
            val kpStart = keypoints[start]
            val kpEnd = keypoints[end]
            if (kpStart == null || kpEnd == null) continue
            if (kpStart.confidence < confidenceThreshold) continue
            if (kpEnd.confidence < confidenceThreshold) continue

            drawLine(
                color = BONE_COLOR,
                start = Offset(kpStart.x * w, kpStart.y * h),
                end = Offset(kpEnd.x * w, kpEnd.y * h),
                strokeWidth = boneWidthPx,
            )
        }

        // ── Draw joint circles ──
        for (i in keypoints.indices) {
            val kp = keypoints[i] ?: continue
            if (kp.confidence < confidenceThreshold) continue
            val color = H36M_JOINT_COLORS.getOrElse(i) { Color.White }
            drawCircle(
                color = color,
                radius = jointRadiusPx,
                center = Offset(kp.x * w, kp.y * h),
            )
        }

        // ── Draw center of mass ──
        if (showCenterOfMass) {
            val pelvis = keypoints[0]
            val thorax = keypoints[8]
            val neck = keypoints[9]
            val head = keypoints[10]
            if (pelvis != null && thorax != null && neck != null && head != null) {
                val comX = (pelvis.x * 0.5f + thorax.x * 0.3f + neck.x * 0.15f + head.x * 0.05f) * w
                val comY = (pelvis.y * 0.5f + thorax.y * 0.3f + neck.y * 0.15f + head.y * 0.05f) * h
                drawCircle(
                    color = Color(red = 0xEF, green = 0x44, blue = 0x44),
                    radius = comRadiusPx,
                    center = Offset(comX, comY),
                )
                // White outline
                drawCircle(
                    color = Color.White,
                    radius = comRadiusPx,
                    center = Offset(comX, comY),
                    style = Stroke(width = comOutlinePx),
                )
            }
        }
    }
}