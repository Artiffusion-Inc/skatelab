// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

object SkateLabShadows {
    // CSS 0 1px 3px rgba(0,0,0,0.08) → elevation 3.dp, offset approximated by ambient/spot color
    val ambientLow: Modifier
        get() =
            Modifier.shadow(
                elevation = 3.dp,
                ambientColor = Color.Black.copy(alpha = 0.08f),
                spotColor = Color.Black.copy(alpha = 0.08f),
            )

    // CSS 0 4px 12px rgba(0,0,0,0.10)
    val ambientMedium: Modifier
        get() =
            Modifier.shadow(
                elevation = 12.dp,
                ambientColor = Color.Black.copy(alpha = 0.10f),
                spotColor = Color.Black.copy(alpha = 0.10f),
            )

    // CSS 0 8px 24px rgba(0,0,0,0.12)
    val ambientHigh: Modifier
        get() =
            Modifier.shadow(
                elevation = 24.dp,
                ambientColor = Color.Black.copy(alpha = 0.12f),
                spotColor = Color.Black.copy(alpha = 0.12f),
            )
}
