package ru.skatelab.capture.data.camera

import androidx.camera.viewfinder.CameraViewfinder
import androidx.lifecycle.LifecycleOwner
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import ru.skatelab.capture.domain.repository.CameraRepository

@Singleton
class CameraRepositoryImpl
    @Inject
    constructor(
        @ApplicationContext context: android.content.Context,
        private val recorder: CameraXRecorder,
    ) : CameraRepository {

        override val isPreviewReady = recorder.isPreviewReady
        override val isRecording = recorder.isRecording

        override suspend fun bindToLifecycle(lifecycleOwner: LifecycleOwner): Result<Unit> =
            recorder.bindToLifecycle(lifecycleOwner)

        override suspend fun unbind() {
            recorder.unbind()
        }

        override fun setViewfinder(viewfinder: CameraViewfinder?) {
            recorder.setViewfinder(viewfinder)
        }

        override suspend fun startRecording(
            videoFile: File,
            framesFile: File,
        ): Result<CameraRepository.RecordingStartResult> =
            recorder.startRecording(videoFile, framesFile)

        override suspend fun stopRecording(): Result<CameraRepository.RecordingStopResult> =
            recorder.stopRecording()

        override suspend fun release() {
            recorder.release()
        }
    }