// AUTO-GENERATED — do not edit. Source: DESIGN.md
package ru.skatelab.capture.presentation.theme

import android.app.Activity
import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

private val LocalSkateLabColors = staticCompositionLocalOf { SkateLabColors }
private val LocalSkateLabTypography = staticCompositionLocalOf { SkateLabTypographyDefaults }

val SkateLabLightScheme =
    lightColorScheme(
        primary = SkateLabColors.primary,
        onPrimary = SkateLabColors.onPrimary,
        primaryContainer = SkateLabColors.primaryDeep,
        onPrimaryContainer = SkateLabColors.primaryForeground,
        secondary = SkateLabColors.secondary,
        onSecondary = SkateLabColors.secondaryForeground,
        tertiary = SkateLabColors.accentGold,
        onTertiary = SkateLabColors.ink,
        background = SkateLabColors.background,
        onBackground = SkateLabColors.foreground,
        surface = SkateLabColors.card,
        onSurface = SkateLabColors.cardForeground,
        surfaceVariant = SkateLabColors.canvasSoft,
        onSurfaceVariant = SkateLabColors.inkMute,
        error = SkateLabColors.destructive,
        onError = SkateLabColors.destructiveForeground,
        outline = SkateLabColors.border,
        outlineVariant = SkateLabColors.hairline,
        scrim = SkateLabColors.ink.copy(alpha = 0.32f),
        inverseSurface = SkateLabColors.surfaceTealDeep,
        inverseOnSurface = SkateLabColors.primaryForeground,
        inversePrimary = SkateLabColors.surfaceIceSoft,
        surfaceTint = SkateLabColors.primary,
    )

object SkateLabTheme {
    val colors: SkateLabColors
        @Composable
        @ReadOnlyComposable
        get() = LocalSkateLabColors.current

    val typography: SkateLabTypography
        @Composable
        @ReadOnlyComposable
        get() = LocalSkateLabTypography.current
}

@Composable
fun AppTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    dynamicColor: Boolean = false,
    content: @Composable () -> Unit,
) {
    val colorScheme =
        when {
            dynamicColor && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S -> {
                val context = LocalContext.current
                if (darkTheme) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
            }
            darkTheme -> SkateLabLightScheme // Design is light-only; dark mode not yet implemented
            else -> SkateLabLightScheme
        }

    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as Activity).window
            window.statusBarColor = colorScheme.primary.toArgb()
            WindowCompat.getInsetsController(window, view).isAppearanceLightStatusBars = false
        }
    }

    CompositionLocalProvider(
        LocalSkateLabColors provides SkateLabColors,
        LocalSkateLabTypography provides SkateLabTypographyDefaults,
    ) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = SkateLabTypographyDefaults.toMaterialTypography(),
            content = content,
        )
    }
}

fun SkateLabTypography.toMaterialTypography(): Typography {
    return Typography(
        displayLarge = displayXxl,
        displayMedium = displayXl,
        displaySmall = displayLg,
        headlineLarge = displayMd,
        headlineMedium = headingLg,
        headlineSmall = headingLg,
        titleLarge = bodyStrong,
        titleMedium = buttonMd,
        titleSmall = buttonCap,
        bodyLarge = bodyLg,
        bodyMedium = bodyMd,
        bodySmall = caption,
        labelLarge = buttonMd,
        labelMedium = buttonCap,
        labelSmall = micro,
    )
}
