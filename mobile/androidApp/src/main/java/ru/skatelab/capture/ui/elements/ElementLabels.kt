package ru.skatelab.capture.ui.elements

import androidx.annotation.StringRes
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R

/**
 * Maps a canonical element-type key (`ru.skatelab.shared.models.elementTypes`)
 * to its locale-specific display string resource. Display strings never appear
 * as literals in code (#331) — they live in `strings.xml` (`element_<key>`),
 * so the picker/labels follow the device locale.
 *
 * Unknown keys fall back to the key itself, capitalized — same behaviour the
 * old `elementLabelRu()` had, but now the fallback is locale-agnostic too.
 */
@StringRes
private fun elementStringRes(key: String): Int? =
    when (key) {
        "waltz_jump" -> R.string.element_waltz_jump
        "toe_loop" -> R.string.element_toe_loop
        "flip" -> R.string.element_flip
        "lutz" -> R.string.element_lutz
        "salchow" -> R.string.element_salchow
        "loop" -> R.string.element_loop
        "axel" -> R.string.element_axel
        "three_turn" -> R.string.element_three_turn
        "spin" -> R.string.element_spin
        else -> null
    }

/**
 * Locale-aware display label for an element-type key, for use inside a
 * `@Composable` (e.g. a `Text`). Unknown keys fall back to the capitalized key.
 */
@Composable
fun elementLabel(key: String): String {
    val res = elementStringRes(key)
    return if (res != null) {
        stringResource(res)
    } else {
        key.replaceFirstChar { it.uppercase() }
    }
}
