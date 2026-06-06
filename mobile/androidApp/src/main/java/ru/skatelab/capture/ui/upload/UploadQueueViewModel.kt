package ru.skatelab.capture.ui.upload

import androidx.work.ExistingWorkPolicy
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.WorkManager
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.capture.upload.UploadScheduler

@HiltViewModel
class UploadQueueViewModel
    @Inject
    constructor(
        private val pendingUploadDao: PendingUploadDao,
        @ApplicationContext private val appContext: android.content.Context,
    ) : ViewModel() {
        val uploads: StateFlow<List<PendingUploadEntity>> =
            pendingUploadDao.getAll()
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

        val pendingCount: StateFlow<Int> =
            pendingUploadDao.countPending()
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

        fun retry(uploadId: String) {
            viewModelScope.launch {
                pendingUploadDao.resetForRetry(uploadId)
                UploadScheduler.enqueue(appContext, uploadId, ExistingWorkPolicy.REPLACE)
            }
        }

        fun cancel(uploadId: String) {
            viewModelScope.launch {
                WorkManager.getInstance(appContext).cancelUniqueWork("upload-$uploadId")
                pendingUploadDao.delete(uploadId)
            }
        }
    }
