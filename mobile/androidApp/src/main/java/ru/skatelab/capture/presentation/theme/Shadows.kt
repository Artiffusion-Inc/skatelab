// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.graphics.BlurMaskFilter
import android.graphics.Paint
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

fun Modifier.shadow(
    offsetX: Dp = 0.dp,
    offsetY: Dp = 0.dp,
    blurRadius: Dp = 0.dp,
    color: Color = Color.Black,
): Modifier =
    this.then(
        Modifier.drawBehind {
            if (blurRadius == 0.dp) return@drawBehind
            val paint =
                Paint().apply {
                    isAntiAlias = true
                    this.color = color.toArgb()
                    maskFilter = BlurMaskFilter(blurRadius.toPx(), BlurMaskFilter.Blur.NORMAL)
                }
            drawIntoCanvas { canvas ->
                canvas.nativeCanvas.save()
                canvas.nativeCanvas.translate(offsetX.toPx(), offsetY.toPx())
                canvas.nativeCanvas.drawRect(0f, 0f, size.width, size.height, paint)
                canvas.nativeCanvas.restore()
            }
        },
    )

object SkateLabShadows {
    val ambientLow: Modifier
        get() =
            Modifier.shadow(
                offsetX = 0.dp,
                offsetY = 1.dp,
                blurRadius = 3.dp,
                color = Color.Black.copy(alpha = 0.08f),
            )

    val ambientMedium: Modifier
        get() =
            Modifier.shadow(
                offsetX = 0.dp,
                offsetY = 4.dp,
                blurRadius = 12.dp,
                color = Color.Black.copy(alpha = 0.10f),
            )

    val ambientHigh: Modifier
        get() =
            Modifier.shadow(
                offsetX = 0.dp,
                offsetY = 8.dp,
                blurRadius = 24.dp,
                color = Color.Black.copy(alpha = 0.12f),
            )
}
