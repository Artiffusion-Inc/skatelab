// AUTO-GENERATED — do not edit. Source: DESIGN.md
// Regenerate: task design:build

package ru.skatelab.capture.presentation.theme

import android.app.Activity
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

// Material 3 bridge — best-effort mapping for standard Material components.
// Custom SkateLab components should use SkateLabTheme.colors.* directly.
private val SkateLabLightScheme =
    lightColorScheme(
        primary = SkateLabColors.primary,
        onPrimary = SkateLabColors.primaryForeground,
        primaryContainer = SkateLabColors.surfaceTealDeep,
        onPrimaryContainer = SkateLabColors.surfaceIceSoft,
        secondary = SkateLabColors.inkMute,
        onSecondary = SkateLabColors.onPrimary,
        tertiary = SkateLabColors.surfaceIceSoft,
        background = SkateLabColors.canvas,
        onBackground = SkateLabColors.ink,
        surface = SkateLabColors.canvas,
        onSurface = SkateLabColors.ink,
        surfaceVariant = SkateLabColors.canvasSoft,
        onSurfaceVariant = SkateLabColors.inkMute,
        outline = SkateLabColors.hairline,
        outlineVariant = SkateLabColors.hairlineDark,
        error = SkateLabColors.destructive,
        onError = SkateLabColors.onPrimary,
    )

object SkateLabTheme {
    val colors: SkateLabColors
        @Composable get() = SkateLabColors

    val typography: SkateLabTypography
        @Composable get() = SkateLabTypographyDefaults
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            @Suppress("DEPRECATION")
            window.statusBarColor = SkateLabColors.primaryDeep.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    MaterialTheme(
        colorScheme = SkateLabLightScheme,
        typography = SkateLabTypographyDefaults.toMaterialTypography(),
        content = content,
    )
}

private fun SkateLabTypography.toMaterialTypography(): Typography =
    Typography(
        displayLarge = displayXxl,
        displayMedium = displayXl,
        displaySmall = displayLg,
        headlineLarge = displayMd,
        headlineMedium = headingLg,
        headlineSmall = headingLg,
        titleLarge = bodyLg,
        titleMedium = bodyStrong,
        titleSmall = bodyMd,
        bodyLarge = bodyLg,
        bodyMedium = bodyMd,
        bodySmall = caption,
        labelLarge = buttonMd,
        labelMedium = buttonCap,
        labelSmall = micro,
    )
