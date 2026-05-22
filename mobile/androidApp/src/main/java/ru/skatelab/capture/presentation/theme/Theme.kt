// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat

// ── Light-only color scheme ────────────────────────────────────────

val SkateLabLightScheme = lightColorScheme(
    primary = SkateLabColors.primary,
    onPrimary = SkateLabColors.primaryForeground,
    primaryContainer = SkateLabColors.primaryDeep,
    onPrimaryContainer = SkateLabColors.primaryForeground,
    secondary = SkateLabColors.canvasSoft,
    onSecondary = SkateLabColors.ink,
    secondaryContainer = SkateLabColors.canvasSoft,
    onSecondaryContainer = SkateLabColors.ink,
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
    onError = SkateLabColors.primaryForeground,
    errorContainer = SkateLabColors.destructive,
    onErrorContainer = SkateLabColors.primaryForeground,
)

// ── Theme accessors ───────────────────────────────────────────────

object SkateLabTheme {
    val colors: SkateLabColors get() = SkateLabColors
    val typography: SkateLabTypography
        @Composable get() = LocalSkateLabTypography.current
}

// ── Local composition ─────────────────────────────────────────────

import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf

val LocalSkateLabTypography = staticCompositionLocalOf { SkateLabTypographyDefaults }

// ── App theme composable ──────────────────────────────────────────

@Composable
fun AppTheme(
    content: @Composable () -> Unit,
) {
    // Gentle Sea Breeze is light-only; dark mode disabled until properly implemented
    val darkTheme = false // isSystemInDarkTheme()

    val colorScheme = SkateLabLightScheme
    val typography = SkateLabTypographyDefaults

    // ── Status bar ─────────────────────────────────────────────────
    val view = (androidx.compose.ui.platform.LocalView.current)
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = SkateLabColors.primaryDeep.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    CompositionLocalProvider(LocalSkateLabTypography provides typography) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = toMaterialTypography(typography),
            content = content,
        )
    }
}

// ── Material Typography bridge ────────────────────────────────────

/**
 * Maps SkateLabTypography tokens to Material3 Typography so that
 * MaterialTheme.typography.* returns sensible defaults from the design system.
 */
fun toMaterialTypography(tokens: SkateLabTypography): Typography {
    val base = weightOrFallback()
    return Typography(
        displayLarge = tokens.displayXxl,
        displayMedium = tokens.displayXl,
        displaySmall = tokens.displayLg,
        headlineLarge = tokens.displayMd,
        headlineMedium = tokens.headingLg,
        headlineSmall = tokens.headingLg.copy(fontSize = 18.sp),
        titleLarge = tokens.bodyLg,
        titleMedium = tokens.bodyMd,
        titleSmall = tokens.caption,
        bodyLarge = tokens.bodyLg,
        bodyMedium = tokens.bodyMd,
        bodySmall = tokens.caption,
        labelLarge = tokens.buttonMd,
        labelMedium = tokens.buttonCap,
        labelSmall = tokens.micro,
    )
}
