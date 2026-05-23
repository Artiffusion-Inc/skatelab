// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.app.Activity
import android.os.Build
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val SkateLabLightScheme =
    lightColorScheme(
        primary = SkateLabColors.primary,
        onPrimary = SkateLabColors.primaryForeground,
        primaryContainer = SkateLabColors.primaryDeep,
        onPrimaryContainer = SkateLabColors.primaryForeground,
        secondary = SkateLabColors.secondary,
        onSecondary = SkateLabColors.secondaryForeground,
        secondaryContainer = SkateLabColors.canvasSoft,
        onSecondaryContainer = SkateLabColors.ink,
        tertiary = SkateLabColors.surfaceIceSoft,
        onTertiary = SkateLabColors.primary,
        tertiaryContainer = SkateLabColors.surfaceIceSoft,
        onTertiaryContainer = SkateLabColors.primary,
        background = SkateLabColors.background,
        onBackground = SkateLabColors.foreground,
        surface = SkateLabColors.canvas,
        onSurface = SkateLabColors.ink,
        surfaceVariant = SkateLabColors.canvasSoft,
        onSurfaceVariant = SkateLabColors.inkMute,
        surfaceTint = SkateLabColors.primary,
        inverseSurface = SkateLabColors.surfaceTealDeep,
        inverseOnSurface = SkateLabColors.primaryForeground,
        error = SkateLabColors.destructive,
        onError = SkateLabColors.primaryForeground,
        errorContainer = SkateLabColors.destructive.copy(alpha = 0.1f),
        onErrorContainer = SkateLabColors.destructive,
        outline = SkateLabColors.hairline,
        outlineVariant = SkateLabColors.hairlineDark,
        scrim = SkateLabColors.surfaceTealDeep.copy(alpha = 0.5f),
    )

object SkateLabTheme {
    val colors: SkateLabColors
        @Composable
        get() = SkateLabColors

    val typography: SkateLabTypography
        @Composable
        get() = SkateLabTypographyDefaults
}

fun SkateLabTypography.toMaterialTypography(): Typography {
    return Typography(
        displayLarge = this.displayXxl,
        displayMedium = this.displayXl,
        displaySmall = this.displayLg,
        headlineLarge = this.displayMd,
        headlineMedium = this.headingLg,
        headlineSmall = this.headingLg,
        titleLarge = this.bodyLg,
        titleMedium = this.bodyMd,
        titleSmall = this.caption,
        bodyLarge = this.bodyLg,
        bodyMedium = this.bodyMd,
        bodySmall = this.caption,
        labelLarge = this.buttonMd,
        labelMedium = this.buttonCap,
        labelSmall = this.micro,
    )
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val colorScheme = SkateLabLightScheme
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window
            window?.let {
                WindowCompat.getInsetsController(it, view).isAppearanceLightStatusBars = true
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) {
                    it.statusBarColor = android.graphics.Color.TRANSPARENT
                } else {
                    it.statusBarColor = colorScheme.background.toArgb()
                }
            }
        }
    }

    MaterialTheme(
        colorScheme = colorScheme,
        typography = SkateLabTypographyDefaults.toMaterialTypography(),
        content = content,
    )
}
