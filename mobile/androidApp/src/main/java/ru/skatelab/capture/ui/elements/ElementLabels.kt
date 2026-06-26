package ru.skatelab.capture.ui.elements

import androidx.annotation.StringRes
import androidx.compose.runtime.Composable
import androidx.compose.ui.res.stringResource
import ru.skatelab.capture.R

/**
 * Maps a canonical ISU element code (`ru.skatelab.shared.models.elementTypes`)
 * to its locale-specific full-name string resource. Display names never appear
 * as literals in code (#331) — they live in `strings.xml`
 * (`element_<code-lowercased>_name`), so the picker/labels follow the device
 * locale. The code itself (e.g. `"3A"`, `"StSq4"`) is locale-agnostic and is
 * shown verbatim alongside the name by [elementLabel].
 *
 * Resource names are the lowercased code (AAPT rejects uppercase resource-name
 * chars), e.g. `"3A"` -> `R.string.element_3a_name`.
 *
 * Unknown keys fall back to the key itself, capitalized — same behaviour the
 * old slug-based `elementLabelRu()` had, but now the fallback is
 * locale-agnostic too.
 */
@StringRes
private fun elementStringRes(key: String): Int? =
    when (key) {
        "1A" -> R.string.element_1a_name
        "2A" -> R.string.element_2a_name
        "3A" -> R.string.element_3a_name
        "4A" -> R.string.element_4a_name
        "1T" -> R.string.element_1t_name
        "2T" -> R.string.element_2t_name
        "3T" -> R.string.element_3t_name
        "4T" -> R.string.element_4t_name
        "1S" -> R.string.element_1s_name
        "2S" -> R.string.element_2s_name
        "3S" -> R.string.element_3s_name
        "4S" -> R.string.element_4s_name
        "1Lo" -> R.string.element_1lo_name
        "2Lo" -> R.string.element_2lo_name
        "3Lo" -> R.string.element_3lo_name
        "4Lo" -> R.string.element_4lo_name
        "1F" -> R.string.element_1f_name
        "2F" -> R.string.element_2f_name
        "3F" -> R.string.element_3f_name
        "4F" -> R.string.element_4f_name
        "1Lz" -> R.string.element_1lz_name
        "2Lz" -> R.string.element_2lz_name
        "3Lz" -> R.string.element_3lz_name
        "4Lz" -> R.string.element_4lz_name
        "1Eu" -> R.string.element_1eu_name
        "CSp1" -> R.string.element_csp1_name
        "CSp2" -> R.string.element_csp2_name
        "CSp3" -> R.string.element_csp3_name
        "CSp4" -> R.string.element_csp4_name
        "StSq1" -> R.string.element_stsq1_name
        "StSq2" -> R.string.element_stsq2_name
        "StSq3" -> R.string.element_stsq3_name
        "StSq4" -> R.string.element_stsq4_name
        "ChSq1" -> R.string.element_chsq1_name
        else -> null
    }

/**
 * Locale-aware display label for an ISU element code, for use inside a
 * `@Composable` (e.g. a `Text`). Renders the code verbatim followed by the
 * localized full name: `elementLabel("3A")` -> `"3A — Triple Axel"` (en) /
 * `"3A — Тройной Аксель"` (ru). The code is locale-agnostic and stable across
 * builds; the name follows the device locale. Unknown keys fall back to the
 * capitalized key.
 */
@Composable
fun elementLabel(key: String): String {
    val res = elementStringRes(key)
    return if (res != null) {
        "$key — ${stringResource(res)}"
    } else {
        key.replaceFirstChar { it.uppercase() }
    }
}
