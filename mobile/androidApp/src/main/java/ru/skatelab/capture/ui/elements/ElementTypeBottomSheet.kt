package ru.skatelab.capture.ui.elements

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.elementTypes

/**
 * Derives the family key of an ISU element code for picker grouping.
 *
 * Jumps are `<rot><family>` (leading digit) — the family is the alpha suffix:
 * `"1A"` -> `"A"`, `"1Lo"` -> `"Lo"`, `"1Eu"` -> `"Eu"`. Spins, step sequences
 * and the choreographic sequence are `<family><level>` (trailing digit) — the
 * family is the alpha prefix: `"CSp1"` -> `"CSp"`, `"StSq4"` -> `"StSq"`,
 * `"ChSq1"` -> `"ChSq"`.
 */
private fun familyOf(code: String): String =
    if (code.first().isDigit()) {
        code.dropWhile { it.isDigit() }
    } else {
        code.dropLastWhile { it.isDigit() }
    }

@StringRes
private fun familyHeaderRes(family: String): Int =
    when (family) {
        "A" -> R.string.element_family_a
        "T" -> R.string.element_family_t
        "S" -> R.string.element_family_s
        "Lo" -> R.string.element_family_lo
        "F" -> R.string.element_family_f
        "Lz" -> R.string.element_family_lz
        "Eu" -> R.string.element_family_eu
        "CSp" -> R.string.element_family_csp
        "StSq" -> R.string.element_family_stsq
        "ChSq" -> R.string.element_family_chsq
        else -> R.string.element_family_a
    }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ElementTypeBottomSheet(
    selectedType: String,
    onTypeSelected: (String) -> Unit,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var currentSelection by remember(selectedType) { mutableStateOf(selectedType) }

    // Group the canonical catalog by family, preserving first-occurrence order
    // (jumps by family, then combination spins, step sequences, choreo). Each
    // family renders as a header with its rotation/level variants as options.
    val families = elementTypes.groupBy { familyOf(it) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        modifier = modifier.testTag("elementTypeSheet"),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.element_type_title),
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(modifier = Modifier.height(16.dp))

            Column(modifier = Modifier.selectableGroup()) {
                families.forEach { (family, codes) ->
                    Text(
                        text = stringResource(familyHeaderRes(family)),
                        style = MaterialTheme.typography.titleSmall,
                        modifier =
                            Modifier
                                .fillMaxWidth()
                                .padding(top = 12.dp, bottom = 4.dp)
                                .testTag("elementFamilyHeader_$family"),
                    )
                    codes.forEach { key ->
                        Row(
                            modifier =
                                Modifier
                                    .fillMaxWidth()
                                    .selectable(
                                        selected = currentSelection == key,
                                        onClick = {
                                            currentSelection = key
                                            onTypeSelected(key)
                                        },
                                        role = Role.RadioButton,
                                    )
                                    .padding(vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            RadioButton(
                                selected = currentSelection == key,
                                onClick = null,
                            )
                            Text(
                                text = elementLabel(key),
                                modifier = Modifier.padding(start = 12.dp),
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            Button(
                onClick = onConfirm,
                modifier = Modifier.fillMaxWidth().testTag("elementTypeConfirm"),
            ) {
                Text(stringResource(R.string.element_type_next))
            }
        }
    }
}
