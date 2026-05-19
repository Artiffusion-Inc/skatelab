package ru.skatelab.capture.presentation.sessiondetail

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import ru.skatelab.capture.AppLogger
import ru.skatelab.capture.data.imu.ImuParser
import ru.skatelab.capture.domain.model.CaptureSession
import ru.skatelab.capture.domain.model.ImuChartData
import ru.skatelab.capture.domain.repository.SessionRepository

@HiltViewModel
class SessionDetailViewModel
    @Inject
    constructor(
        private val sessionRepository: SessionRepository,
        private val appLogger: AppLogger,
    ) : ViewModel() {
        private val _session = MutableStateFlow<CaptureSession?>(null)
        val session: StateFlow<CaptureSession?> = _session.asStateFlow()

        private val _imuData = MutableStateFlow<ImuChartData?>(null)
        val imuData: StateFlow<ImuChartData?> = _imuData.asStateFlow()

        private val _isImuLoading = MutableStateFlow(false)
        val isImuLoading: StateFlow<Boolean> = _isImuLoading.asStateFlow()

        private val _playbackPositionMs = MutableStateFlow(0L)
        val playbackPositionMs: StateFlow<Long> = _playbackPositionMs.asStateFlow()

        fun updatePlaybackPosition(positionMs: Long) {
            _playbackPositionMs.value = positionMs
        }

        @Suppress("ktlint:standard:property-naming")
        private var _exoPlayer: ExoPlayer? = null

        fun loadSession(sessionId: String) {
            viewModelScope.launch {
                _session.value = sessionRepository.getSession(sessionId)
                appLogger.i(TAG, "Session loaded: id=$sessionId session=${_session.value?.id}")
            }
        }

        fun getPlayer(context: Context): ExoPlayer {
            return _exoPlayer ?: ExoPlayer.Builder(context).build().also {
                it.addListener(playerListener)
                _exoPlayer = it
                appLogger.i(TAG, "ExoPlayer created")
            }
        }

        fun setVideoSource(player: ExoPlayer) {
            val session =
                _session.value ?: run {
                    appLogger.w(TAG, "setVideoSource: session is null, skipping")
                    return
                }
            val videoFile = session.videoFile
            appLogger.i(
                TAG,
                "setVideoSource: file=${videoFile.absolutePath} exists=${videoFile.exists()} length=${videoFile.length()} canRead=${videoFile.canRead()}",
            )
            if (videoFile.exists()) {
                val uri = Uri.fromFile(videoFile)
                appLogger.i(TAG, "setVideoSource: uri=$uri")
                player.setMediaItem(MediaItem.fromUri(uri))
                player.playWhenReady = true
                player.prepare()
                appLogger.i(TAG, "setVideoSource: prepare() called, playWhenReady=true")
            } else {
                appLogger.e(TAG, "setVideoSource: video file does not exist at ${videoFile.absolutePath}")
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

        private val playerListener =
            object : Player.Listener {
                override fun onPlaybackStateChanged(playbackState: Int) {
                    val state =
                        when (playbackState) {
                            Player.STATE_IDLE -> "IDLE"
                            Player.STATE_BUFFERING -> "BUFFERING"
                            Player.STATE_READY -> "READY"
                            Player.STATE_ENDED -> "ENDED"
                            else -> "UNKNOWN"
                        }
                    appLogger.i(TAG, "ExoPlayer state: $state")
                }

                override fun onPlayerError(error: PlaybackException) {
                    appLogger.e(TAG, "ExoPlayer error: ${error.message} cause=${error.cause?.message}")
                }

                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    appLogger.i(TAG, "ExoPlayer playing: $isPlaying")
                }
            }

        companion object {
            private const val TAG = "SessionDetailVM"
        }

        override fun onCleared() {
            super.onCleared()
            _exoPlayer?.removeListener(playerListener)
            _exoPlayer?.release()
            _exoPlayer = null
        }
    }
