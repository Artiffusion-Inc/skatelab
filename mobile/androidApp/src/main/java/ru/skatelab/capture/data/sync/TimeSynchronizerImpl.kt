package ru.skatelab.capture.data.sync

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import ru.skatelab.capture.domain.model.SensorId
import ru.skatelab.capture.domain.service.TimeSynchronizer
import ru.skatelab.capture.domain.usecase.ConfigureSensorTimeUseCase

@Singleton
class TimeSynchronizerImpl
    @Inject
    constructor(
        private val periodicTimeSync: PeriodicTimeSync,
        private val timeSyncManager: TimeSyncManager,
        private val configureSensorTimeUseCase: ConfigureSensorTimeUseCase,
    ) : TimeSynchronizer {
        companion object {
            private const val OFFSET_THRESHOLD_NS = 1_000_000_000L // 1 second
        }

        override fun sync(scope: CoroutineScope) {
            scope.launch {
                // Auto time-config: write Android time to sensor if offset is
                // unknown (=0, first sync) or exceeds 1 second.
                // Runs BEFORE periodicTimeSync to avoid race — WT901 ignores
                // register reads while processing time-config writes.
                for (sensorId in listOf(SensorId.LEFT, SensorId.RIGHT)) {
                    val offset = timeSyncManager.getOffset(sensorId)
                    if (offset == 0L || kotlin.math.abs(offset) > OFFSET_THRESHOLD_NS) {
                        configureSensorTimeUseCase(sensorId).onFailure {
                            // Best effort — proceed with offset-based sync
                        }
                    }
                }
                periodicTimeSync.sync(scope)
            }
        }

        override suspend fun awaitSync() = periodicTimeSync.awaitSync()

        override fun stop() = periodicTimeSync.stop()

        override fun getOffset(sensorId: SensorId): Long = timeSyncManager.getOffset(sensorId)
    }
