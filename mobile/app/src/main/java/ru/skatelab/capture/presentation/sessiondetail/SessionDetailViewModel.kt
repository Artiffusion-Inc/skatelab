package ru.skatelab.capture.presentation.sessiondetail

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import dagger.hilt.android.lifecycle.HiltViewModel
import java.io.File
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.imu.ImuParser
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.ImuChartData
import ru.skatelab.capture.domain.repository.SessionRepository

@HiltViewModel
class SessionDetailViewModel
    @Inject
    constructor(
        private val sessionRepository: SessionRepository,
    ) : ViewModel() {
        private val _session = MutableStateFlow<CaptureSession?>(null)
        val session: StateFlow<CaptureSession?> = _session.asStateFlow()

        private val _imuData = MutableStateFlow<ImuChartData?>(null)
        val imuData: StateFlow<ImuChartData?> = _imuData.asStateFlow()

        private val _isImuLoading = MutableStateFlow(false)
        val isImuLoading: StateFlow<Boolean> = _isImuLoading.asStateFlow()

        private var _exoPlayer: ExoPlayer? = null

        fun loadSession(sessionId: String) {
            viewModelScope.launch {
                _session.value = sessionRepository.getSession(sessionId)
            }
        }

        fun getPlayer(context: Context): ExoPlayer {
            return _exoPlayer ?: ExoPlayer.Builder(context).build().also {
                _session.value?.let { session ->
                    if (session.videoFile.exists()) {
                        it.setMediaItem(
                            MediaItem.fromUri(Uri.fromFile(session.videoFile)),
                        )
                        it.prepare()
                    }
                }
                _exoPlayer = it
            }
        }

        fun loadImuData() {
            val session = _session.value ?: return
            if (_imuData.value != null || _isImuLoading.value) return

            viewModelScope.launch(Dispatchers.IO) {
                _isImuLoading.value = true
                try {
                    _imuData.value = ImuParser.parse(session.imuLeftFile, session.imuRightFile)
                } finally {
                    _isImuLoading.value = false
                }
            }
        }

        override fun onCleared() {
            super.onCleared()
            _exoPlayer?.release()
            _exoPlayer = null
        }
    }
