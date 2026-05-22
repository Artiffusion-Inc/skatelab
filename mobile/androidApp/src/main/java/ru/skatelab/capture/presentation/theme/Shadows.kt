// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * SkateLab shadow vocabulary — Flat-By-Default.
 *
 * Shadows only appear on floating overlays (dropdowns, modals, popovers)
 * in response to interaction. No shadows on static cards, containers, or banners.
 */
object SkateLabShadows {

    /**
     * Ambient Low — 0 1px 3px rgba(0,0,0,0.08)
     * Use: Active tab, selected chip.
     */
    val ambientLow: Modifier = Modifier
        .shadow(
            elevation = 1.dp,
            ambientColor = Color(0x14000000),  // rgba(0,0,0,0.08)
            spotColor = Color(0x14000000),
        )

    /**
     * Ambient Medium — 0 4px 12px rgba(0,0,0,0.10)
     * Use: Dropdown menus, popovers.
     */
    val ambientMedium: Modifier = Modifier
        .shadow(
            elevation = 4.dp,
            ambientColor = Color(0x1A000000),  // rgba(0,0,0,0.10)
            spotColor = Color(0x1A000000),
        )

    /**
     * Ambient High — 0 8px 24px rgba(0,0,0,0.12)
     * Use: Modals, floating toolbars.
     */
    val ambientHigh: Modifier = Modifier
        .shadow(
            elevation = 8.dp,
            ambientColor = Color(0x1F000000),  // rgba(0,0,0,0.12)
            spotColor = Color(0x1F000000),
        )
}
