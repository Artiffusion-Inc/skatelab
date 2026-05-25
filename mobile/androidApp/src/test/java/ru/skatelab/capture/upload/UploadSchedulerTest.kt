package ru.skatelab.capture.upload

import org.junit.Assert.assertEquals
import org.junit.Test

class UploadSchedulerTest {
    @Test
    fun uploadWorker_inputData_keyMatches() {
        val data = UploadWorker.inputData("abc-123")
        assertEquals("abc-123", data.getString(UploadWorker.KEY_UPLOAD_ID))
    }

    @Test
    fun uploadWorker_inputData_emptyString() {
        val data = UploadWorker.inputData("")
        assertEquals("", data.getString(UploadWorker.KEY_UPLOAD_ID))
    }

    @Test
    fun uploadWorker_keyUploadId_constant() {
        assertEquals("upload_id", UploadWorker.KEY_UPLOAD_ID)
    }
}
