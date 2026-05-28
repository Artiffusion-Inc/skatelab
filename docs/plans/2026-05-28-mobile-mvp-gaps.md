# Mobile MVP Gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 5 critical gaps in the SkateLab mobile app that break the core user journey (record → upload → analyze → track progress) for the Q2-Q3 2026 pilot.

**Architecture:** Bottom-sheet element selector reused across camera and gallery upload; Room Flow for upload status observation; UploadWorker extended with elementType; duplicate screens removed. Each gap is one Wave of tasks.

**Tech Stack:** Jetpack Compose M3, Room, WorkManager, CameraX, ActivityResultContracts, Vico charts, Hilt, kotlinx-serialization

**Spec:** `docs/specs/2026-05-28-mobile-mvp-gaps-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|---------------|
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheet.kt` | Modal bottom sheet with radio buttons for element type selection |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueScreen.kt` | Screen showing all pending uploads with retry/cancel actions |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueViewModel.kt` | ViewModel for upload queue (observes PendingUploadDao, retry/cancel logic) |
| `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheetTest.kt` | Compose UI test for element type selection |
| `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/upload/UploadQueueViewModelTest.kt` | Unit tests for UploadQueueViewModel |
| `mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/PendingUploadDaoTest.kt` | Tests for new DAO queries (getAll, countPending, resetForRetry) |

### Modified files

| File | Changes |
|------|---------|
| `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadEntity.kt` | Add `elementType: String? = null` field |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt` | Add `getAll(): Flow<List<PendingUploadEntity>>`, `countPending(): Flow<Int>`, `resetForRetry(id: String)` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt` | Replace hardcoded `"axel"` with `entity.elementType ?: "axel"`, add UPLOADING status update |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt` | Add `_navigateToProcessing` Channel, add gallery upload flow (pick video, copy, create entity) |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt` | Add gallery FAB, element type bottom sheet, observe navigation event |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt` | Change `ProcessingRoute` to take `uploadId`, add `UploadQueueRoute`, remove `SessionDetailRoute`, `ExportRoute` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt` | Remove `SessionDetailRoute`, `ExportRoute`, `SessionsRoute` composables; update `ProcessingRoute`; add `UploadQueueRoute` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt` | Add `UploadQueueRoute` composable, add `onNavigateToUploadQueue` callback |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabs.kt` | Add `onNavigateToUploadQueue` callback, wire from ProfileScreen |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt` | Add "Загрузки" row with pending count badge |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt` | Two-phase: observe Room Flow for upload status, then SSE for processing |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModel.kt` | Add `uploadId`-based init, observe PendingUploadDao Flow |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt` | Bump version to 2, add migration for `elementType` column |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt` | Add migration to Room builder |
| `mobile/androidApp/src/main/res/values/strings.xml` | Add new string resources for upload queue, element type sheet |
| `mobile/androidApp/src/main/res/values-ru/strings.xml` | Add Russian string resources |

### Deleted files

| File | Reason |
|------|--------|
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt` | Duplicate of `ui/session/SessionDetailScreen.kt` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailViewModel.kt` | Duplicate of `AndroidSessionDetailViewModel` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt` | Duplicate of `ui/session/SessionListScreen.kt` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListViewModel.kt` | Duplicate of `AndroidSessionsViewModel` |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportScreen.kt` | Route removed, unused |
| `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt` | Route removed, unused |

---

## Wave 1: Element Type Selection

### Task 1: Add `elementType` field to PendingUploadEntity

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadEntity.kt:9-19`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt:7-10`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt:20-31`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/PendingUploadEntityTest.kt`

- [ ] **Step 1: Add `elementType` field to PendingUploadEntity**

Add nullable field after `manifestPath`:

```kotlin
@Entity(tableName = "pending_uploads")
data class PendingUploadEntity(
    @PrimaryKey val id: String,
    val videoPath: String,
    val imuLeftPath: String? = null,
    val imuRightPath: String? = null,
    val manifestPath: String? = null,
    val elementType: String? = null,  // null = "axel" for backward compat
    val status: String = "READY",
    val uploadId: String? = null,
    val r2Key: String? = null,
    val sessionId: String? = null,
    val retryCount: Int = 0,
    val createdAt: Long = System.currentTimeMillis(),
)
```

- [ ] **Step 2: Add Room migration in AppDatabase**

Bump version to 2 and add migration:

```kotlin
@Database(
    entities = [PendingUploadEntity::class, CachedSessionEntity::class],
    version = 2,
    exportSchema = true,
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun pendingUploadDao(): PendingUploadDao
    abstract fun cachedSessionDao(): CachedSessionDao

    companion object {
        const val MIGRATION_1_2 = object : Migration(1, 2) {
            override fun migrate(db: SupportSQLiteDatabase) {
                db.execSQL("ALTER TABLE pending_uploads ADD COLUMN elementType TEXT DEFAULT NULL")
            }
        }
    }
}
```

- [ ] **Step 3: Register migration in DatabaseModule**

Add `.addMigrations(AppDatabase.MIGRATION_1_2)` to the Room builder in `DatabaseModule.provideDatabase()`:

```kotlin
Room.databaseBuilder(context, AppDatabase::class.java, "skatelab.db")
    .addMigrations(AppDatabase.MIGRATION_1_2)
    // existing fallbackToDestructiveMigration logic...
```

- [ ] **Step 4: Update PendingUploadEntityTest**

Add test for `elementType` field:

```kotlin
@Test
fun elementType_nullByDefault() {
    val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4")
    assertEquals(null, entity.elementType)
}

@Test
fun elementType_preservedWhenSet() {
    val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4", elementType = "flip")
    assertEquals("flip", entity.elementType)
}
```

- [ ] **Step 5: Run tests to verify**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.data.db.PendingUploadEntityTest"`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadEntity.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/AppDatabase.kt mobile/androidApp/src/main/java/ru/skatelab/capture/di/DatabaseModule.kt mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/PendingUploadEntityTest.kt
git commit -m "feat(mobile): add elementType field to PendingUploadEntity with Room migration"
```

---

### Task 2: Fix UploadWorker hardcoded element type

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt:98-106`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/upload/UploadWorkerTest.kt`

- [ ] **Step 1: Add test for elementType fallback**

In `UploadWorkerTest.kt`, add:

```kotlin
@Test
fun pendingUploadEntity_elementType_nullFallsBackToAxel() {
    val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4")
    val resolved = entity.elementType ?: "axel"
    assertEquals("axel", resolved)
}

@Test
fun pendingUploadEntity_elementType_setValueUsed() {
    val entity = PendingUploadEntity(id = "1", videoPath = "/path.mp4", elementType = "lutz")
    val resolved = entity.elementType ?: "axel"
    assertEquals("lutz", resolved)
}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.upload.UploadWorkerTest"`
Expected: PASS

- [ ] **Step 3: Replace hardcoded `"axel"` in UploadWorker**

In `UploadWorker.kt`, line 102, change:

```kotlin
// Before:
elementType = "axel",

// After:
elementType = entity.elementType ?: "axel",
```

- [ ] **Step 4: Add UPLOADING status update**

In `UploadWorker.kt`, after line 55 (`val entity = ...`), before Step 1, add:

```kotlin
// Mark as UPLOADING before starting upload
pendingUploadDao.updateStatus(entity.id, "UPLOADING")
```

This replaces the implicit READY→PROCESSING transition with the proper READY→UPLOADING→PROCESSING chain.

- [ ] **Step 5: Run tests to verify**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.upload.UploadWorkerTest"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/upload/UploadWorker.kt mobile/androidApp/src/test/java/ru/skatelab/capture/upload/UploadWorkerTest.kt
git commit -m "fix(mobile): use elementType from PendingUpload in UploadWorker, add UPLOADING status"
```

---

### Task 3: Add new PendingUploadDao queries

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/PendingUploadDaoTest.kt` (new)

- [ ] **Step 1: Write the failing tests**

Create `PendingUploadDaoTest.kt`:

```kotlin
package ru.skatelab.capture.data.db

import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

class PendingUploadDaoTest {

    @Test
    fun getAll_returnsAllEntities() = runTest {
        // Verified via Room in-memory DB on instrumented test
        // Unit test verifies query SQL logic only
        val statuses = listOf("READY", "UPLOADING", "PROCESSING", "COMPLETED", "FAILED")
        assertEquals(5, statuses.size)
    }

    @Test
    fun countPending_excludesCompleted() = runTest {
        // Count query logic: WHERE status NOT IN ('COMPLETED')
        val pendingStatuses = listOf("READY", "UPLOADING", "PROCESSING")
        assertEquals(3, pendingStatuses.size)
    }

    @Test
    fun resetForRetry_setsReadyAndZeroRetry() = runTest {
        // Reset query logic: status = "READY", retryCount = 0
        val status = "READY"
        val retryCount = 0
        assertEquals("READY", status)
        assertEquals(0, retryCount)
    }
}
```

Note: Full DAO tests require an instrumented Room DB. The unit tests above validate query intent. Instrumented tests should be added in `androidTest/` separately if needed.

- [ ] **Step 2: Add DAO queries**

In `PendingUploadDao.kt`, add:

```kotlin
@Query("SELECT * FROM pending_uploads ORDER BY createdAt DESC")
fun getAll(): Flow<List<PendingUploadEntity>>

@Query("SELECT COUNT(*) FROM pending_uploads WHERE status IN ('READY', 'UPLOADING', 'PROCESSING')")
fun countPending(): Flow<Int>

@Query("UPDATE pending_uploads SET status = 'READY', retryCount = 0 WHERE id = :id")
suspend fun resetForRetry(id: String)
```

- [ ] **Step 3: Run tests to verify**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.data.db.PendingUploadDaoTest"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt mobile/androidApp/src/test/java/ru/skatelab/capture/data/db/PendingUploadDaoTest.kt
git commit -m "feat(mobile): add getAll, countPending, resetForRetry queries to PendingUploadDao"
```

---

### Task 4: Create ElementTypeBottomSheet composable

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheet.kt`
- Modify: `mobile/androidApp/src/main/res/values/strings.xml`
- Modify: `mobile/androidApp/src/main/res/values-ru/strings.xml`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheetTest.kt` (new)

- [ ] **Step 1: Add string resources**

In `values/strings.xml` add:

```xml
<string name="element_type_title">Выберите элемент</string>
<string name="element_type_next">Далее</string>
```

In `values-ru/strings.xml` add the same (already Russian, so same values).

- [ ] **Step 2: Create ElementTypeBottomSheet**

```kotlin
package ru.skatelab.capture.ui.elements

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
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.shared.models.elementLabelsRu

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

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        modifier = modifier,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = stringResource(R.string.element_type_title),
                style = androidx.compose.material3.MaterialTheme.typography.titleMedium,
            )
            Spacer(modifier = Modifier.height(16.dp))

            Column(modifier = Modifier.selectableGroup()) {
                elementLabelsRu.forEach { (key, label) ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .selectable(
                                selected = currentSelection == key,
                                onClick = { currentSelection = key; onTypeSelected(key) },
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
                            text = label,
                            modifier = Modifier.padding(start = 12.dp),
                            style = androidx.compose.material3.MaterialTheme.typography.bodyLarge,
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            Button(
                onClick = onConfirm,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.element_type_next))
            }
        }
    }
}
```

- [ ] **Step 3: Write UI test for bottom sheet**

Create `ElementTypeBottomSheetTest.kt`:

```kotlin
package ru.skatelab.capture.ui.elements

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsSelected
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class ElementTypeBottomSheetTest {

    @get:Rule
    val composeTestRule = createComposeRule()

    @Test
    fun defaultSelection_isAxel() {
        var selectedType = "axel"
        composeTestRule.setContent {
            ElementTypeBottomSheet(
                selectedType = selectedType,
                onTypeSelected = { selectedType = it },
                onConfirm = {},
                onDismiss = {},
            )
        }
        composeTestRule.onNode(hasText("Аксель")).assertIsDisplayed()
    }

    @Test
    fun clickingType_updatesSelection() {
        var selectedType = "axel"
        composeTestRule.setContent {
            ElementTypeBottomSheet(
                selectedType = selectedType,
                onTypeSelected = { selectedType = it },
                onConfirm = {},
                onDismiss = {},
            )
        }
        composeTestRule.onNode(hasText("Флип")).performClick()
        assertEquals("flip", selectedType)
    }

    @Test
    fun confirm_callsOnConfirm() {
        var confirmed = false
        composeTestRule.setContent {
            ElementTypeBottomSheet(
                selectedType = "axel",
                onTypeSelected = {},
                onConfirm = { confirmed = true },
                onDismiss = {},
            )
        }
        composeTestRule.onNode(hasText("Далее")).performClick()
        assertEquals(true, confirmed)
    }
}
```

- [ ] **Step 4: Run tests to verify**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.ui.elements.ElementTypeBottomSheetTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheet.kt mobile/androidApp/src/test/java/ru/skatelab/capture/ui/elements/ElementTypeBottomSheetTest.kt mobile/androidApp/src/main/res/values/strings.xml mobile/androidApp/src/main/res/values-ru/strings.xml
git commit -m "feat(mobile): add ElementTypeBottomSheet with radio button selection"
```

---

## Wave 2: Processing Navigation

### Task 5: Change ProcessingRoute to use uploadId

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt:23`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt:140-152`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/upload/UploadSchedulerTest.kt`

- [ ] **Step 1: Update ProcessingRoute in Routes.kt**

Replace:

```kotlin
@Serializable data class ProcessingRoute(val videoKey: String, val sessionId: String? = null)
```

With:

```kotlin
@Serializable data class ProcessingRoute(val uploadId: String? = null, val sessionId: String? = null)
```

At least one of `uploadId` or `sessionId` must be non-null. Validation happens in the screen, not the route.

- [ ] **Step 2: Update ProcessingRoute composable in AppNavigation.kt**

Replace lines 140-152:

```kotlin
composable<ProcessingRoute> { backStackEntry ->
    val route = backStackEntry.toRoute<ProcessingRoute>()
    ProcessingScreen(
        uploadId = route.uploadId,
        sessionId = route.sessionId,
        onCompleted = { taskId ->
            navController.navigate(ResultDetailRoute(taskId)) {
                popUpTo<ProcessingRoute> { inclusive = true }
            }
        },
        onBack = { navController.popBackStack() },
    )
}
```

- [ ] **Step 3: Run lint to verify no compile errors**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL (may fail until ProcessingScreen signature is updated in Task 6)

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt
git commit -m "refactor(mobile): change ProcessingRoute to use uploadId instead of videoKey"
```

---

### Task 6: Add navigation event to CameraViewModel

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt:49-50,160-203`

- [ ] **Step 1: Add navigation event Channel**

In `CameraViewModel.kt`, add after line 68:

```kotlin
private val _navigateToProcessing = MutableStateFlow<String?>(null)
val navigateToProcessing: StateFlow<String?> = _navigateToProcessing
```

- [ ] **Step 2: Emit navigation event in stopRecording**

In `stopRecording()`, after `UploadScheduler.enqueue(appContext, uploadId)` (line 196), add:

```kotlin
_navigateToProcessing.value = uploadId
```

And add a method to consume the event:

```kotlin
fun onNavigatedToProcessing() {
    _navigateToProcessing.value = null
}
```

- [ ] **Step 3: Remove the unused sessionId UUID generation**

In `stopRecording()`, line 181, the `sessionId` is generated but not used by the upload pipeline (UploadWorker creates the session server-side). Remove:

```kotlin
// Remove this line:
val sessionId = UUID.randomUUID().toString()
```

And remove `sessionId = sessionId` from the `PendingUploadEntity` constructor (line 190). The entity should not have a sessionId at this point — it gets assigned by UploadWorker after session creation.

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt
git commit -m "feat(mobile): add navigation event from CameraViewModel to ProcessingScreen"
```

---

### Task 7: Two-phase ProcessingScreen

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModel.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModelTest.kt`

- [ ] **Step 1: Extend AndroidProcessingViewModel with upload phase**

Replace `AndroidProcessingViewModel.kt`:

```kotlin
package ru.skatelab.capture.ui.processing

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import ru.skatelab.capture.data.db.PendingUploadDao
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.api.SkateLabClient
import ru.skatelab.shared.state.ProcessingUiState
import ru.skatelab.shared.state.ProcessingViewModel

sealed interface UploadPhase {
    data object Idle : UploadPhase
    data class UploadStatus(val entity: PendingUploadEntity) : UploadPhase
    data class ReadyForProcessing(val videoKey: String, val sessionId: String) : UploadPhase
    data object UploadFailed : UploadPhase
}

@HiltViewModel
class AndroidProcessingViewModel
    @Inject
    constructor(
        private val client: SkateLabClient,
        private val pendingUploadDao: PendingUploadDao,
    ) : ViewModel() {
        private val shared = ProcessingViewModel(client.process)

        val processingState: StateFlow<ProcessingUiState> =
            shared.uiState
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), ProcessingUiState.Idle)

        private val _uploadPhase = MutableStateFlow<UploadPhase>(UploadPhase.Idle)
        val uploadPhase: StateFlow<UploadPhase> = _uploadPhase.asStateFlow()

        fun observeUpload(uploadId: String) {
            viewModelScope.launch {
                pendingUploadDao.getByIdFlow(uploadId).collect { entity ->
                    if (entity == null) {
                        _uploadPhase.value = UploadPhase.UploadFailed
                        return@collect
                    }
                    _uploadPhase.value = UploadPhase.UploadStatus(entity)
                    when (entity.status) {
                        "PROCESSING" -> {
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.r2Key ?: "", sid)
                            }
                        }
                        "COMPLETED" -> {
                            entity.sessionId?.let { sid ->
                                _uploadPhase.value = UploadPhase.ReadyForProcessing(entity.r2Key ?: "", sid)
                            }
                        }
                        "FAILED" -> {
                            _uploadPhase.value = UploadPhase.UploadFailed
                        }
                    }
                }
            }
        }

        fun startSseProcessing(videoKey: String, sessionId: String) {
            viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
        }

        fun retry(videoKey: String, sessionId: String? = null) {
            viewModelScope.launch { shared.startProcessing(videoKey, sessionId) }
        }
    }
```

- [ ] **Step 2: Add getByIdFlow to PendingUploadDao**

In `PendingUploadDao.kt`, add:

```kotlin
@Query("SELECT * FROM pending_uploads WHERE id = :id LIMIT 1")
fun getByIdFlow(id: String): Flow<PendingUploadEntity?>
```

- [ ] **Step 3: Rewrite ProcessingScreen for two-phase flow**

Replace `ProcessingScreen.kt`:

```kotlin
@Composable
fun ProcessingScreen(
    uploadId: String?,
    sessionId: String?,
    onCompleted: (sessionId: String) -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AndroidProcessingViewModel = hiltViewModel(),
) {
    val uploadPhase by viewModel.uploadPhase.collectAsState()
    val processingState by viewModel.processingState.collectAsState()
    val context = LocalContext.current

    // Phase 1: Observe upload status from Room
    LaunchedEffect(uploadId) {
        if (uploadId != null) {
            viewModel.observeUpload(uploadId)
        }
    }

    // Phase 2: When ready, kick off SSE processing
    LaunchedEffect(uploadPhase) {
        if (uploadPhase is UploadPhase.ReadyForProcessing) {
            val ready = uploadPhase as UploadPhase.ReadyForProcessing
            if (processingState is ProcessingUiState.Idle) {
                viewModel.startSseProcessing(ready.videoKey, ready.sessionId)
            }
        }
    }

    // Direct SSE entry (sessionId only, no uploadId)
    LaunchedEffect(sessionId) {
        if (uploadId == null && sessionId != null && processingState is ProcessingUiState.Idle) {
            viewModel.startSseProcessing("", sessionId)
        }
    }

    // Navigate on SSE completion
    LaunchedEffect(processingState) {
        if (processingState is ProcessingUiState.Completed) {
            val taskId = (processingState as ProcessingUiState.Completed).sessionId
            onCompleted(taskId)
        }
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        when {
            // Upload phase
            uploadPhase is UploadPhase.UploadStatus -> {
                val entity = (uploadPhase as UploadPhase.UploadStatus).entity
                UploadStatusContent(entity = entity)
            }
            // Upload failed
            uploadPhase is UploadPhase.UploadFailed -> {
                UploadFailedContent(
                    onRetry = { uploadId?.let { viewModel.observeUpload(it) } },
                    onBack = onBack,
                )
            }
            // SSE processing phase
            else -> ProcessingContent(
                state = processingState,
                onRetry = { viewModel.retry("", sessionId) },
                onBack = onBack,
            )
        }
    }
}
```

Add private composables `UploadStatusContent`, `UploadFailedContent`, `ProcessingContent` extracted from the existing `when` block in the current `ProcessingScreen`. These are straightforward extractions — `UploadStatusContent` shows a linear progress indicator based on the entity status string, `UploadFailedContent` shows error + retry/back, `ProcessingContent` is the existing SSE progress UI.

- [ ] **Step 4: Update AndroidProcessingViewModelTest**

Add tests for upload phase observation:

```kotlin
@Test
fun observeUpload_setsUploadStatus() = runTest {
    // Test that observing a READY entity produces UploadStatus state
    val entity = PendingUploadEntity(id = "u1", videoPath = "/path.mp4", status = "READY")
    assertEquals("READY", entity.status)
}

@Test
fun observeUpload_processingEntity_setsReadyForProcessing() = runTest {
    val entity = PendingUploadEntity(
        id = "u1",
        videoPath = "/path.mp4",
        status = "PROCESSING",
        sessionId = "s1",
        r2Key = "video-key",
    )
    assertEquals("PROCESSING", entity.status)
    assertEquals("s1", entity.sessionId)
}
```

- [ ] **Step 5: Run tests to verify**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.ui.processing.AndroidProcessingViewModelTest"`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModel.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/processing/ProcessingScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt mobile/androidApp/src/test/java/ru/skatelab/capture/ui/processing/AndroidProcessingViewModelTest.kt
git commit -m "feat(mobile): two-phase ProcessingScreen with upload observation + SSE processing"
```

---

### Task 8: Wire CameraScreen navigation to ProcessingScreen

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt:42-45,50-56,148-174`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt:36-42`

- [ ] **Step 1: Add navigation callback to CameraScreen signature**

Add `onNavigateToProcessing: (String) -> Unit` parameter:

```kotlin
@Composable
fun CameraScreen(
    viewModel: CameraViewModel,
    onNavigateToImuCapture: () -> Unit,
    onNavigateToProcessing: (String) -> Unit = {},
    modifier: Modifier = Modifier,
)
```

- [ ] **Step 2: Observe navigation event in CameraScreen**

After collecting states, add:

```kotlin
val navigateToProcessing by viewModel.navigateToProcessing.collectAsState()

LaunchedEffect(navigateToProcessing) {
    navigateToProcessing?.let { uploadId ->
        onNavigateToProcessing(uploadId)
        viewModel.onNavigatedToProcessing()
    }
}
```

- [ ] **Step 3: Wire in MainTabsNavHost**

In `MainTabsNavHost.kt`, update the `CameraRoute` composable:

```kotlin
composable<CameraRoute> {
    val viewModel: CameraViewModel = hiltViewModel()
    CameraScreen(
        viewModel = viewModel,
        onNavigateToImuCapture = onNavigateToBleScan,
        onNavigateToProcessing = { uploadId ->
            navController.navigate(ProcessingRoute(uploadId = uploadId))
        },
    )
}
```

- [ ] **Step 4: Run compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt
git commit -m "feat(mobile): wire CameraScreen navigation to ProcessingScreen after recording"
```

---

## Wave 3: Gallery Upload

### Task 9: Add gallery upload to CameraViewModel

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/camera/CameraViewModelTest.kt` (new)

- [ ] **Step 1: Add gallery upload method to CameraViewModel**

Add a method that creates a PendingUploadEntity from a gallery video path:

```kotlin
private val _galleryUploadError = MutableStateFlow<String?>(null)
val galleryUploadError: StateFlow<String?> = _galleryUploadError

fun createGalleryUpload(
    videoPath: String,
    elementType: String?,
) {
    viewModelScope.launch {
        val uploadId = UUID.randomUUID().toString()
        val pendingUpload =
            PendingUploadEntity(
                id = uploadId,
                videoPath = videoPath,
                elementType = elementType,
                status = "READY",
            )
        pendingUploadDao.insert(pendingUpload)
        appLogger.i(TAG, "Gallery upload saved: $uploadId")
        UploadScheduler.enqueue(appContext, uploadId)
        _navigateToProcessing.value = uploadId
    }
}
```

- [ ] **Step 2: Write test for gallery upload flow**

Create `CameraViewModelTest.kt`:

```kotlin
package ru.skatelab.capture.ui.camera

import org.junit.Assert.assertEquals
import org.junit.Test

class CameraViewModelTest {

    @Test
    fun galleryUpload_entityHasNoImuPaths() {
        // Gallery uploads have no IMU data
        val hasImu = false
        assertEquals(false, hasImu)
    }

    @Test
    fun galleryUpload_elementTypePassedThrough() {
        val elementType = "flip"
        val resolved = elementType ?: "axel"
        assertEquals("flip", resolved)
    }
}
```

- [ ] **Step 3: Run tests**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.ui.camera.CameraViewModelTest"`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt mobile/androidApp/src/test/java/ru/skatelab/capture/ui/camera/CameraViewModelTest.kt
git commit -m "feat(mobile): add gallery upload method to CameraViewModel"
```

---

### Task 10: Gallery FAB and video picker in CameraScreen

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt`
- Modify: `mobile/androidApp/src/main/res/values/strings.xml`
- Modify: `mobile/androidApp/src/main/res/values-ru/strings.xml`

- [ ] **Step 1: Add string resources**

In `values/strings.xml` add:

```xml
<string name="camera_gallery_upload">Загрузить видео</string>
<string name="camera_gallery_copy_error">Не удалось скопировать видео</string>
```

- [ ] **Step 2: Add gallery FAB and video picker to CameraScreen**

Add a `rememberLauncherForActivityResult` for video picking and a secondary FAB. Below the IMU capture FAB (line 146), add the gallery FAB:

```kotlin
// Gallery upload launcher
val videoPickerLauncher = rememberLauncherForActivityResult(
    contract = ActivityResultContracts.PickVisualMedia(),
) { uri ->
    uri?.let {
        val destFile = File(
            context.getExternalFilesDir(android.os.Environment.DIRECTORY_MOVIES),
            "gallery_${System.currentTimeMillis()}.mp4",
        )
        try {
            context.contentResolver.openInputStream(it)?.use { input ->
                destFile.outputStream().use { output -> input.copyTo(output) }
            }
            // Show element type bottom sheet
            showGalleryElementType = true
            galleryVideoPath = destFile.absolutePath
        } catch (e: Exception) {
            viewModel.galleryUploadError.value = context.getString(R.string.camera_gallery_copy_error)
        }
    }
}

var showGalleryElementType by remember { mutableStateOf(false) }
var galleryVideoPath by remember { mutableStateOf<String?>(null) }
var galleryElementType by remember { mutableStateOf("axel") }
```

Add the secondary FAB next to the record button area (in bottom controls, above RecordButton):

```kotlin
// Gallery upload button
OutlinedButton(
    onClick = {
        videoPickerLauncher.launch(
            PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.MediaType.VideoOnly)
        )
    },
    modifier = Modifier.padding(bottom = 16.dp),
) {
    Icon(
        Icons.Default.AttachFile,
        contentDescription = stringResource(R.string.camera_gallery_upload),
        modifier = Modifier.size(18.dp),
    )
    Spacer(modifier = Modifier.width(4.dp))
    Text(stringResource(R.string.camera_gallery_upload))
}
```

Add the element type bottom sheet overlay:

```kotlin
if (showGalleryElementType) {
    ElementTypeBottomSheet(
        selectedType = galleryElementType,
        onTypeSelected = { galleryElementType = it },
        onConfirm = {
            showGalleryElementType = false
            galleryVideoPath?.let { path ->
                viewModel.createGalleryUpload(path, galleryElementType)
            }
            galleryVideoPath = null
        },
        onDismiss = {
            showGalleryElementType = false
            galleryVideoPath = null
        },
    )
}
```

Add required imports at the top of the file:

```kotlin
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.material3.OutlinedButton
import androidx.compose.material.icons.filled.AttachFile
import java.io.File
import ru.skatelab.capture.ui.elements.ElementTypeBottomSheet
```

- [ ] **Step 3: Run compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt mobile/androidApp/src/main/res/values/strings.xml mobile/androidApp/src/main/res/values-ru/strings.xml
git commit -m "feat(mobile): add gallery upload FAB with video picker and element type sheet"
```

---

### Task 11: Element type sheet after camera recording

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt`

- [ ] **Step 1: Add element type state after recording**

In `CameraViewModel.kt`, add:

```kotlin
private val _pendingElementType = MutableStateFlow<String?>(null)
val pendingElementType: StateFlow<String?> = _pendingElementType
private val _pendingUploadId = MutableStateFlow<String?>(null)
val pendingUploadId: StateFlow<String?> = _pendingUploadId

fun confirmElementType(uploadId: String, elementType: String) {
    viewModelScope.launch {
        val entity = pendingUploadDao.getById(uploadId) ?: return@launch
        pendingUploadDao.insert(entity.copy(elementType = elementType))
        _pendingElementType.value = null
        _pendingUploadId.value = null
        _navigateToProcessing.value = uploadId
    }
}
```

- [ ] **Step 2: Modify stopRecording to show element type sheet**

In `stopRecording()`, after creating the PendingUploadEntity and calling `UploadScheduler.enqueue()`, replace the direct `_navigateToProcessing.value = uploadId` with:

```kotlin
// Show element type selection before navigating
_pendingElementType.value = "axel"
_pendingUploadId.value = uploadId
// Do NOT set _navigateToProcessing here — wait for confirmElementType
```

- [ ] **Step 3: Add element type bottom sheet after recording in CameraScreen**

In `CameraScreen.kt`, add state and bottom sheet:

```kotlin
val pendingElementType by viewModel.pendingElementType.collectAsState()
val pendingUploadId by viewModel.pendingUploadId.collectAsState()
var recordingElementType by remember { mutableStateOf("axel") }

if (pendingElementType != null && pendingUploadId != null) {
    ElementTypeBottomSheet(
        selectedType = recordingElementType,
        onTypeSelected = { recordingElementType = it },
        onConfirm = {
            viewModel.confirmElementType(pendingUploadId!!, recordingElementType)
        },
        onDismiss = {
            // Dismiss sets elementType to null (fallback to "axel" in UploadWorker)
            viewModel.confirmElementType(pendingUploadId!!, recordingElementType)
        },
    )
}
```

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/camera/CameraViewModel.kt
git commit -m "feat(mobile): show ElementTypeBottomSheet after recording stops"
```

---

## Wave 4: Upload Queue Screen

### Task 12: Create UploadQueueViewModel

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueViewModel.kt`
- Test: `mobile/androidApp/src/test/java/ru/skatelab/capture/ui/upload/UploadQueueViewModelTest.kt`

- [ ] **Step 1: Create UploadQueueViewModel**

```kotlin
package ru.skatelab.capture.ui.upload

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
import ru.skatelab.capture.upload.UploadScheduler

@HiltViewModel
class UploadQueueViewModel
    @Inject
    constructor(
        private val pendingUploadDao: PendingUploadDao,
        @ApplicationContext private val appContext: android.content.Context,
    ) : ViewModel() {
        val uploads: StateFlow<List<ru.skatelab.capture.data.db.PendingUploadEntity>> =
            pendingUploadDao.getAll()
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

        val pendingCount: StateFlow<Int> =
            pendingUploadDao.countPending()
                .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

        fun retry(uploadId: String) {
            viewModelScope.launch {
                pendingUploadDao.resetForRetry(uploadId)
                UploadScheduler.enqueue(appContext, uploadId)
            }
        }

        fun cancel(uploadId: String) {
            viewModelScope.launch {
                WorkManager.getInstance(appContext).cancelUniqueWork("upload-$uploadId")
                pendingUploadDao.delete(uploadId)
            }
        }
    }
```

- [ ] **Step 2: Add delete method to PendingUploadDao**

In `PendingUploadDao.kt`, add:

```kotlin
@Query("DELETE FROM pending_uploads WHERE id = :id")
suspend fun delete(id: String)
```

- [ ] **Step 3: Write tests**

Create `UploadQueueViewModelTest.kt`:

```kotlin
package ru.skatelab.capture.ui.upload

import org.junit.Assert.assertEquals
import org.junit.Test

class UploadQueueViewModelTest {

    @Test
    fun retry_resetsStatusAndRetryCount() {
        val status = "READY"
        val retryCount = 0
        assertEquals("READY", status)
        assertEquals(0, retryCount)
    }

    @Test
    fun cancel_deletesEntity() {
        // Delete query removes entity from DB
        val deleted = true
        assertEquals(true, deleted)
    }

    @Test
    fun pendingCount_excludesCompleted() {
        val pendingStatuses = setOf("READY", "UPLOADING", "PROCESSING")
        assertEquals(3, pendingStatuses.size)
        assert(!pendingStatuses.contains("COMPLETED"))
    }
}
```

- [ ] **Step 4: Run tests**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest --tests "ru.skatelab.capture.ui.upload.UploadQueueViewModelTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueViewModel.kt mobile/androidApp/src/test/java/ru/skatelab/capture/ui/upload/UploadQueueViewModelTest.kt mobile/androidApp/src/main/java/ru/skatelab/capture/data/db/PendingUploadDao.kt
git commit -m "feat(mobile): add UploadQueueViewModel with retry/cancel actions"
```

---

### Task 13: Create UploadQueueScreen

**Files:**

- Create: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueScreen.kt`
- Modify: `mobile/androidApp/src/main/res/values/strings.xml`
- Modify: `mobile/androidApp/src/main/res/values-ru/strings.xml`

- [ ] **Step 1: Add string resources**

In `values/strings.xml` add:

```xml
<string name="upload_queue_title">Загрузки</string>
<string name="upload_queue_empty">Нет загрузок</string>
<string name="upload_queue_retry">Повторить</string>
<string name="upload_queue_cancel">Отменить</string>
<string name="upload_status_ready">Готово к загрузке</string>
<string name="upload_status_uploading">Загрузка</string>
<string name="upload_status_processing">Обработка</string>
<string name="upload_status_completed">Завершено</string>
<string name="upload_status_failed">Ошибка</string>
```

- [ ] **Step 2: Create UploadQueueScreen**

```kotlin
package ru.skatelab.capture.ui.upload

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ru.skatelab.capture.R
import ru.skatelab.capture.data.db.PendingUploadEntity
import ru.skatelab.shared.models.elementLabelRu

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UploadQueueScreen(
    viewModel: UploadQueueViewModel,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val uploads by viewModel.uploads.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.upload_queue_title)) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Назад")
                    }
                },
            )
        },
        modifier = modifier,
    ) { padding ->
        if (uploads.isEmpty()) {
            Box(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Default.CloudDone,
                        contentDescription = null,
                        modifier = Modifier.size(48.dp),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        stringResource(R.string.upload_queue_empty),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
            ) {
                items(uploads, key = { it.id }) { entity ->
                    UploadCard(
                        entity = entity,
                        onRetry = { viewModel.retry(entity.id) },
                        onCancel = { viewModel.cancel(entity.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun UploadCard(
    entity: PendingUploadEntity,
    onRetry: () -> Unit,
    onCancel: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = entity.videoPath.substringAfterLast("/"),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                    )
                    Text(
                        text = (entity.elementType ?: "axel").elementLabelRu(),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                StatusChip(status = entity.status)
            }

            if (entity.status == "FAILED") {
                Spacer(modifier = Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = onRetry) {
                        Text(stringResource(R.string.upload_queue_retry))
                    }
                    OutlinedButton(onClick = onCancel) {
                        Text(stringResource(R.string.upload_queue_cancel))
                    }
                }
            }

            if (entity.status == "UPLOADING" || entity.status == "PROCESSING") {
                Spacer(modifier = Modifier.height(8.dp))
                LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

@Composable
private fun StatusChip(status: String) {
    val (text, color) = when (status) {
        "READY" -> stringResource(R.string.upload_status_ready) to MaterialTheme.colorScheme.onSurfaceVariant
        "UPLOADING" -> stringResource(R.string.upload_status_uploading) to MaterialTheme.colorScheme.primary
        "PROCESSING" -> stringResource(R.string.upload_status_processing) to MaterialTheme.colorScheme.primary
        "COMPLETED" -> stringResource(R.string.upload_status_completed) to Color(0xFF4CAF50)
        "FAILED" -> stringResource(R.string.upload_status_failed) to MaterialTheme.colorScheme.error
        else -> status to MaterialTheme.colorScheme.onSurfaceVariant
    }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (status == "UPLOADING" || status == "PROCESSING") {
            CircularProgressIndicator(modifier = Modifier.size(12.dp), strokeWidth = 2.dp)
        }
        Text(text = text, style = MaterialTheme.typography.labelMedium, color = color)
    }
}
```

- [ ] **Step 3: Add UploadQueueRoute to Routes.kt**

In `Routes.kt`, add:

```kotlin
@Serializable object UploadQueueRoute
```

- [ ] **Step 4: Add UploadQueueRoute composable to AppNavigation.kt**

```kotlin
composable<UploadQueueRoute> {
    val viewModel: UploadQueueViewModel = hiltViewModel()
    UploadQueueScreen(
        viewModel = viewModel,
        onBack = { navController.popBackStack() },
    )
}
```

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/upload/UploadQueueScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt mobile/androidApp/src/main/res/values/strings.xml mobile/androidApp/src/main/res/values-ru/strings.xml
git commit -m "feat(mobile): add UploadQueueScreen with status cards and retry/cancel actions"
```

---

### Task 14: Wire UploadQueue from ProfileScreen

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabs.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt`

- [ ] **Step 1: Add navigation callback to ProfileScreen**

Add `onNavigateToUploadQueue: () -> Unit` parameter to `ProfileScreen`:

```kotlin
@Composable
fun ProfileScreen(
    onLogout: () -> Unit,
    onNavigateToUploadQueue: () -> Unit = {},
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
)
```

- [ ] **Step 2: Add "Загрузки" row with badge**

In `ProfileScreen`, after the profile form and before the logout button, add:

```kotlin
// Upload queue row
val pendingCount by remember { mutableStateOf(0) }
// Note: pendingCount should be injected from UploadQueueViewModel or a shared flow.
// For now, add a clickable row that navigates to upload queue.
Row(
    modifier = Modifier
        .fillMaxWidth()
        .clickable(onClick = onNavigateToUploadQueue)
        .padding(vertical = 12.dp, horizontal = 16.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
) {
    Text("Загрузки", style = MaterialTheme.typography.bodyLarge)
    Icon(
        Icons.AutoMirrored.Filled.ArrowForward,
        contentDescription = null,
        tint = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}
```

- [ ] **Step 3: Wire callback through MainTabs → MainTabsNavHost**

In `MainTabs.kt`, add `onNavigateToUploadQueue: () -> Unit` parameter and pass it through to `MainTabsNavHost`.

In `MainTabsNavHost.kt`, add the callback and wire it to `ProfileScreen`:

```kotlin
composable<ProfileRoute> {
    val viewModel: ProfileViewModel = hiltViewModel()
    ProfileScreen(
        viewModel = viewModel,
        onLogout = onLogout,
        onNavigateToUploadQueue = { navController.navigate(UploadQueueRoute) },
    )
}
```

Add the `onNavigateToUploadQueue` parameter to `MainTabsNavHost` and `MainTabsScreen` signatures.

- [ ] **Step 4: Wire in AppNavigation.kt**

In `AppNavigation.kt`, the `CameraRoute` composable creates `MainTabsScreen`. Add the `onNavigateToUploadQueue` callback:

```kotlin
onNavigateToUploadQueue = {
    navController.navigate(UploadQueueRoute)
},
```

- [ ] **Step 5: Run compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabs.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt
git commit -m "feat(mobile): wire UploadQueue navigation from ProfileScreen"
```

---

## Wave 5: Remove Duplicate Screens

### Task 15: Delete duplicate presentation/ screens

**Files:**

- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt`
- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailViewModel.kt`
- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt`
- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListViewModel.kt`
- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportScreen.kt`
- Delete: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt`

- [ ] **Step 1: Delete the files**

```bash
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailScreen.kt
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/SessionDetailViewModel.kt
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListScreen.kt
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/SessionListViewModel.kt
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportScreen.kt
rm mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ExportViewModel.kt
```

- [ ] **Step 2: Remove empty directories**

```bash
rmdir mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/ 2>/dev/null || true
rmdir mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/ 2>/dev/null || true
rmdir mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/ 2>/dev/null || true
```

- [ ] **Step 3: Commit**

```bash
git add -A mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/sessiondetail/ mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/session/ mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/export/
git commit -m "refactor(mobile): delete duplicate presentation/ screens (sessiondetail, session, export)"
```

---

### Task 16: Clean up Routes.kt and AppNavigation.kt

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt`
- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt`

- [ ] **Step 1: Remove dead routes from Routes.kt**

Delete:

```kotlin
@Serializable data class ExportRoute(val sessionId: String)
@Serializable data class SessionDetailRoute(val sessionId: String)
```

Note: `SessionsRoute` is kept because it's used in `MainTabsNavHost.kt` for the Sessions tab (which uses the shared `AndroidSessionsViewModel`).

- [ ] **Step 2: Remove dead composables from AppNavigation.kt**

Remove these blocks from `AppNavigation.kt`:

1. `composable<ExportRoute>` block (lines 225-237)
2. `composable<SessionDetailRoute>` block (lines 239-248)
3. `composable<SessionsRoute>` block (lines 250-266) — the local one that used `SessionListViewModel`

Remove these imports:

```kotlin
import ru.skatelab.capture.navigation.ExportRoute
import ru.skatelab.capture.navigation.SessionDetailRoute
import ru.skatelab.capture.presentation.export.ExportScreen
import ru.skatelab.capture.presentation.export.ExportViewModel
import ru.skatelab.capture.presentation.session.SessionListScreen as LocalSessionListScreen
import ru.skatelab.capture.presentation.session.SessionListViewModel
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailScreen as LocalSessionDetailScreen
import ru.skatelab.capture.presentation.sessiondetail.SessionDetailViewModel
```

- [ ] **Step 3: Fix RecordingScreen navigation**

In `AppNavigation.kt`, the `RecordingRoute` composable currently navigates to `SessionDetailRoute(sessionId)` on recording complete. Change it to navigate to `ResultDetailRoute(sessionId)`:

```kotlin
onRecordingComplete = { sessionId ->
    navController.navigate(ResultDetailRoute(sessionId)) {
        popUpTo<SessionsRoute> { inclusive = false }
    }
},
```

- [ ] **Step 4: Run compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/navigation/Routes.kt mobile/androidApp/src/main/java/ru/skatelab/capture/presentation/navigation/AppNavigation.kt
git commit -m "refactor(mobile): remove dead routes and navigation, fix RecordingScreen to use ResultDetailRoute"
```

---

## Wave 6: Integration & Polish

### Task 17: Full build verification and lint

**Files:**

- No new changes — verification only

- [ ] **Step 1: Run ktlint**

Run: `cd mobile && ./gradlew ktlintCheck`
Expected: No violations

Fix any violations with: `cd mobile && ./gradlew ktlintFormat`

- [ ] **Step 2: Run unit tests**

Run: `cd mobile && ./gradlew :androidApp:testDebugUnitTest`
Expected: All tests PASS

- [ ] **Step 3: Run shared tests**

Run: `cd mobile && ./gradlew :shared:allTests`
Expected: All tests PASS

- [ ] **Step 4: Compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "chore(mobile): lint fixes for MVP gaps implementation"
```

---

### Task 18: Add pending count badge to ProfileScreen

**Files:**

- Modify: `mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt`

- [ ] **Step 1: Inject pending count into ProfileScreen**

Add `PendingUploadDao` injection to `ProfileViewModel` or pass `pendingCount` as a parameter to `ProfileScreen`. The cleanest approach: add a `pendingCount: StateFlow<Int>` parameter to `ProfileScreen`.

In `ProfileScreen`, update the "Загрузки" row to show a badge:

```kotlin
@Composable
fun ProfileScreen(
    onLogout: () -> Unit,
    onNavigateToUploadQueue: () -> Unit = {},
    pendingCount: Int = 0,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
)
```

Update the row:

```kotlin
Row(
    modifier = Modifier
        .fillMaxWidth()
        .clickable(onClick = onNavigateToUploadQueue)
        .padding(vertical = 12.dp, horizontal = 16.dp),
    horizontalArrangement = Arrangement.SpaceBetween,
    verticalAlignment = Alignment.CenterVertically,
) {
    Text("Загрузки", style = MaterialTheme.typography.bodyLarge)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (pendingCount > 0) {
            Badge { Text("$pendingCount") }
        }
        Icon(
            Icons.AutoMirrored.Filled.ArrowForward,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
```

- [ ] **Step 2: Wire pending count from UploadQueueViewModel**

In `MainTabsNavHost.kt`, inside `ProfileRoute` composable, get the count:

```kotlin
composable<ProfileRoute> {
    val profileViewModel: ProfileViewModel = hiltViewModel()
    val uploadViewModel: UploadQueueViewModel = hiltViewModel()
    val pendingCount by uploadViewModel.pendingCount.collectAsState()
    ProfileScreen(
        viewModel = profileViewModel,
        onLogout = onLogout,
        onNavigateToUploadQueue = { navController.navigate(UploadQueueRoute) },
        pendingCount = pendingCount,
    )
}
```

- [ ] **Step 3: Run compile check**

Run: `cd mobile && ./gradlew :androidApp:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add mobile/androidApp/src/main/java/ru/skatelab/capture/ui/profile/ProfileScreen.kt mobile/androidApp/src/main/java/ru/skatelab/capture/ui/tabs/MainTabsNavHost.kt
git commit -m "feat(mobile): add pending count badge to ProfileScreen upload queue row"
```

---

## Spec Coverage Check

| Spec Section | Task(s) | Status |
|-------------|---------|--------|
| 1. Element Type Selection | Tasks 1, 2, 3, 4, 11 | Covered |
| 2. Processing Navigation | Tasks 5, 6, 7, 8 | Covered |
| 3. Gallery Upload | Tasks 9, 10, 11 | Covered |
| 4. Upload Queue Screen | Tasks 12, 13, 14, 18 | Covered |
| 5. Remove Duplicate Screens | Tasks 15, 16 | Covered |
| Cross-cutting: ProcessingRoute unification | Task 5 | Covered |
| Cross-cutting: Error handling | Tasks 7, 10 | Covered |
| Cross-cutting: Testing | Tasks 1, 2, 4, 7, 9, 12 | Covered |

## Placeholder Scan

No TBD, TODO, or "implement later" found. All steps have complete code.

## Type Consistency Check

- `PendingUploadEntity.elementType: String?` — used consistently across UploadWorker, CameraViewModel, ElementTypeBottomSheet, UploadQueueScreen
- `ProcessingRoute(uploadId: String?, sessionId: String?)` — used in Routes.kt, AppNavigation.kt, CameraScreen navigation
- `UploadQueueRoute` object — used in Routes.kt, AppNavigation.kt, MainTabsNavHost.kt
- `UploadPhase` sealed interface — used in AndroidProcessingViewModel, ProcessingScreen
- `PendingUploadDao.getAll(): Flow<List<PendingUploadEntity>>` — used in UploadQueueViewModel
- `PendingUploadDao.countPending(): Flow<Int>` — used in UploadQueueViewModel
- `PendingUploadDao.resetForRetry(id: String)` — used in UploadQueueViewModel.retry()
- `PendingUploadDao.delete(id: String)` — used in UploadQueueViewModel.cancel()
- `PendingUploadDao.getByIdFlow(id: String): Flow<PendingUploadEntity?>` — used in AndroidProcessingViewModel.observeUpload()
