package ru.skatelab.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SessionUpdateRequest(
    @SerialName("element_type") val elementType: String? = null,
    /**
     * Kept for source compatibility with older consumers. The sessions PATCH
     * endpoint does not accept notes, so [SessionsApi] never sends this field.
     */
    @Deprecated("The backend sessions PATCH contract has no notes field")
    val notes: String? = null,
    val status: String? = null,
    @SerialName("process_task_id") val processTaskId: String? = null,
    @SerialName("isu_code") val isuCode: String? = null,
)
