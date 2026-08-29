# KMP Skill Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix critical inaccuracies and improve coverage in the kmp-development skill based on 5-agent review findings.

**Architecture:** Incremental edits to existing reference files + 2 new files (networking.md, viewmodels.md) split from shared-code.md. No structural overhaul — targeted fixes per the spec.

**Tech Stack:** Markdown editing, grep for verification

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `~/.agents/skills/kmp-development/SKILL.md` | Modify | Fix Law #6, add `feature` command, add 10 new audit checks |
| `~/.agents/skills/kmp-development/reference/compose-multiplatform.md` | Modify | Fix Navigation 3 artifact, add Hot Reload JVM-only, add Nav 3 alpha status, add CMP 1.11.0 breaking changes, add cross-refs |
| `~/.agents/skills/kmp-development/reference/gradle.md` | Modify | Add CI/CD section, add version freshness note |
| `~/.agents/skills/kmp-development/reference/android-ui.md` | Modify | Expand navigation section |
| `~/.agents/skills/kmp-development/reference/ios-ui.md` | Modify | Fix link format (backtick → markdown) |
| `~/.agents/skills/kmp-development/reference/shared-code.md` | Modify | Trim to ViewModel/coroutines/Flow only |
| `~/.agents/skills/kmp-development/reference/networking.md` | Create | Ktor client, auth, serialization (split from shared-code.md) |
| `~/.agents/skills/kmp-development/reference/viewmodels.md` | Create | ViewModels, coroutines, Flow, state management (split from shared-code.md) |
| `~/.agents/skills/kmp-development/reference/INDEX.md` | Modify | Add networking.md + viewmodels.md, remove shared-code.md row |

---

## Wave 1 — P0 Critical Fixes

### Task 1: Fix Navigation 3 artifact (WRONG)

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/compose-multiplatform.md:52-64`

- [ ] **Step 1: Fix the Navigation 3 artifact line**

Replace lines 52-56:

```markdown
**Navigation 3** (new stack-based API): available via `org.jetbrains.androidx.navigation:navigation-compose3` in CMP 1.10.0+. Manipulates back stack directly.
```

With:

```markdown
**Navigation 3** (new stack-based API): `org.jetbrains.androidx.navigation3:navigation3-ui` version `1.0.0-alpha05`. **Alpha for CMP — not production-ready.** Navigation 2.9+ remains the stable choice. `adaptive-navigation3` available at `1.3.0-alpha02`.
```

- [ ] **Step 2: Verify no other references to the wrong artifact**

Run: `grep -rn "navigation-compose3" ~/.agents/skills/kmp-development/`
Expected: zero hits

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/compose-multiplatform.md
git commit -m "fix(kmp-skill): correct Navigation 3 artifact (WRONG → right)"
```

### Task 2: Fix Law #6 contradiction

**Files:**

- Modify: `~/.agents/skills/kmp-development/SKILL.md:121`

- [ ] **Step 1: Rewrite Law #6 with current/target split**

Replace line 121:

```markdown
6. **Repository in shared, DB in platform** — Repository interfaces in `commonMain`, Room implementations in `androidMain`. iOS uses Keychain + UserDefaults via `multiplatform-settings`.
```

With:

```markdown
6. **Repository in shared, DB in platform** — Repository interfaces in `commonMain`. Room currently lives in `androidApp/data/db/` (migration to `shared/androidMain` planned). iOS uses Keychain + UserDefaults via `multiplatform-settings`.
```

- [ ] **Step 2: Verify Law #6 reflects actual project structure**

Run: `find mobile/androidApp -name "*.kt" -path "*/db/*" | head -5`
Expected: Room files exist in androidApp (confirming the statement)

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/SKILL.md
git commit -m "fix(kmp-skill): law #6 reflect actual Room location (androidApp, not shared)"
```

### Task 3: Add Hot Reload JVM-only clarification

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/compose-multiplatform.md:16`

- [ ] **Step 1: Rewrite Hot Reload line with JVM-only scope**

Replace line 16-17:

```markdown
**Compose Hot Reload**: Stable since 1.10.0. Enabled by default for Kotlin 2.1.20+. No configuration needed.
```

With:

```markdown
**Compose Hot Reload**: Stable since 1.10.0. **Desktop/JVM only** — does not work on iOS or Android. Enabled by default for Kotlin 2.1.20+. `AfterHotReloadEffect` for reload-aware side effects. Limitations: ViewModel state not preserved, single IDE instance.
```

- [ ] **Step 2: Verify Hot Reload scope is explicit**

Run: `grep -n "Hot Reload" ~/.agents/skills/kmp-development/reference/compose-multiplatform.md`
Expected: line mentions "Desktop/JVM only"

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/compose-multiplatform.md
git commit -m "fix(kmp-skill): clarify Hot Reload is desktop/JVM only, not iOS/Android"
```

### Task 4: Expand Navigation 3 alpha status in compose-multiplatform.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/compose-multiplatform.md:54` (already updated in Task 1)

This is covered by Task 1's replacement text which includes "**Alpha for CMP — not production-ready.** Navigation 2.9+ remains the stable choice."

- [ ] **Step 1: Verify Task 1 output includes alpha status**

Run: `grep -n "Alpha\|alpha" ~/.agents/skills/kmp-development/reference/compose-multiplatform.md`
Expected: Navigation 3 alpha status present

- [ ] **Step 2: Commit** (already in Task 1 commit, skip if squashed)

---

## Wave 2 — P1 Audit & Commands

### Task 5: Expand audit command with 10 new ban checks

**Files:**

- Modify: `~/.agents/skills/kmp-development/SKILL.md:73-84`

- [ ] **Step 1: Add 10 new ban checks to the Ban checks table**

After the existing 10 ban checks (after `LiveData in commonMain` row, line 84), add:

```markdown
| runBlocking in commonMain | `commonMain` + `runBlocking` | Blocks native thread, defeats structured concurrency |
| java.util.UUID in commonMain | `commonMain` + `import java.util.UUID` | JVM-only type, crashes on iOS |
| java.time in commonMain | `commonMain` + `import java.time` | JVM-only, use kotlinx-datetime |
| Dispatchers.IO in commonMain | `commonMain` + `Dispatchers.IO` | Android-only dispatcher, use Default |
| StateFlow for UiEffect | `StateFlow<.*Effect` | Re-consumed on config change, use Channel |
| @Entity without tableName | `@Entity(` without `tableName` | Room KMP requires explicit table name |
| fallbackToDestructiveMigration not debug-only | `fallbackToDestructiveMigration` not in debug | Data loss in production |
| @Parcelize in commonMain | `commonMain` + `@Parcelize` | Android-only annotation |
| LocalContext.current in shared Compose | `LocalContext.current` in `shared/` | Android-only, not in commonMain Compose |
| Hardcoded strings in UI composables | String literals in @Composable functions | i18n violation, use string resources |
```

- [ ] **Step 2: Add corresponding absolute bans**

After the existing 10 absolute bans (after "KMP-NativeCoroutines" ban, around line 140), add:

```markdown
- **runBlocking in commonMain.** Blocks native thread. Use `runTest` in tests, structured concurrency elsewhere.
- **java.util.UUID in commonMain.** JVM-only. Use `String` representation + custom serializer.
- **java.time in commonMain.** JVM-only. Use `kotlinx-datetime`.
- **Dispatchers.IO in commonMain.** Android-only dispatcher. Use `Dispatchers.Default` for IO in shared code.
- **StateFlow for effects.** Re-consumed on config change. Use `Channel.receiveAsFlow()`.
- **@Entity without tableName.** Room KMP requires explicit table names. Always add `tableName = "table_name"`.
- **fallbackToDestructiveMigration in release.** Destroys user data. Guard with `BuildConfig.DEBUG`.
- **@Parcelize in commonMain.** Android-only. Use `@Serializable` instead.
- **LocalContext.current in shared Compose.** Android-only. Pass data via parameters or expect/actual.
- **Hardcoded strings in UI composables.** i18n violation. Use string resources.
```

- [ ] **Step 3: Verify new bans are consistent with ban checks**

Run: `grep -c "runBlocking" ~/.agents/skills/kmp-development/SKILL.md`
Expected: 3+ (ban check row + absolute ban + possibly other mentions)

- [ ] **Step 4: Commit**

```bash
git add ~/.agents/skills/kmp-development/SKILL.md
git commit -m "feat(kmp-skill): add 10 new audit ban checks and absolute bans"
```

### Task 6: Add `feature` command to SKILL.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/SKILL.md:39-55`

- [ ] **Step 1: Add `feature` command row to commands table**

After the `test` command row (line 51), add:

```markdown
| `feature` | Workflow | Full feature stack: DTO → Repository → ViewModel → UI → Navigation → Tests | Loads `networking.md` → `data-layer.md` → `viewmodels.md` → `android-ui.md` → `testing.md` sequentially |
```

- [ ] **Step 2: Add routing rule for `feature` command**

After the existing routing rules (after rule 6, around line 66), add:

```markdown
7. `feature` loads 5 reference files sequentially in order: networking → data → viewmodels → android-ui → testing. Never skip or reorder.
```

- [ ] **Step 3: Update the argument-hint in frontmatter**

Replace line 4:

```yaml
argument-hint: "[topic]"
```

With:

```yaml
argument-hint: "[topic] — use 'feature' for full-stack feature creation workflow"
```

- [ ] **Step 4: Verify `feature` command is discoverable**

Run: `grep -n "feature" ~/.agents/skills/kmp-development/SKILL.md`
Expected: command row + routing rule + argument-hint

- [ ] **Step 5: Commit**

```bash
git add ~/.agents/skills/kmp-development/SKILL.md
git commit -m "feat(kmp-skill): add 'feature' command for full-stack feature workflow"
```

---

## Wave 3 — P1 File Splits

### Task 7: Create networking.md (split from shared-code.md)

**Files:**

- Create: `~/.agents/skills/kmp-development/reference/networking.md`
- Modify: `~/.agents/skills/kmp-development/reference/shared-code.md`

- [ ] **Step 1: Create networking.md with Ktor + Auth + Serialization content**

```markdown
# Networking (Ktor, Auth, Serialization)

Ktor client setup, auth interceptors, and serialization config for shared code.

**Topics:** Setup | Ktor client | Auth interceptors | Serialization | Cross-references

## Setup Checklist

Before writing networking code, verify:
1. Engine injection via expect/actual — never create engine in commonMain
2. Single `HttpClient` instance shared across the app
3. `@Serializable` + `@SerialName` on every DTO
4. Repository wraps all API exceptions into `AppError` — see [error-handling.md](error-handling.md)

Where to look in the codebase:
- Client config: `commonMain` `SkateLabClient` class
- Auth: `commonMain` `AuthRepository` + `TokenStorage`
- DTOs: `commonMain` `schemas/` or `dto/` packages

## Ktor Client

**Where:** `SkateLabClient` in `commonMain` — single `Json` instance, single `HttpClient`, configured once.

**Engine injection (expect/actual):** Constructor takes `HttpClientEngine`. Android provides `OkHttp`, iOS provides `Darwin`. Never create the engine inside `commonMain`.

| Platform | Engine | Where |
|----------|--------|-------|
| Android | `OkHttp` | `androidMain` factory |
| iOS | `Darwin` | `iosMain` factory |

**Testing:** Swap `MockEngine` in tests — see [testing.md](testing.md) for MockEngine patterns.

**Common mistake:** Creating `HttpClient()` per request. Each client holds a connection pool and thread pool. Create once, share across the app.

## Auth Interceptors

**Where:** `BearerAuth` plugin installed on `SkateLabClient.httpClient`. Token storage via `TokenStorage` backed by multiplatform-settings (see [data-layer.md](data-layer.md)).

**Pattern:** `install(Auth) { bearer { loadTokens { ... } refreshTokens { ... } } }` — Ktor auto-injects the header and handles 401 refresh.

**`markAsRefreshTokenRequest()`:** Must call this inside `refreshTokens` block on the refresh request. Without it, a 401 on the refresh call itself triggers an infinite retry loop.

**Token storage:** `multiplatform-settings` with platform encryption — `EncryptedSharedPreferences` on Android, `KeychainSettings` on iOS. Never store tokens in plain `SharedPreferences`.

**Common mistake:** Manually adding `Authorization` header per request. No refresh, easy to forget, duplicates logic the plugin already handles.

## Serialization

**Where:** Single `Json` config singleton in `commonMain`, shared by `SkateLabClient` and any standalone serialization.

**Key settings:**

| Setting | When | Why |
|---------|------|-----|
| `ignoreUnknownKeys = true` | Always | Backend adds fields? No crash |
| `encodeDefaults = true` | PATCH endpoints | Server sees explicit defaults, not omitted fields |
| `isLenient = true` | Most APIs | Relaxed parsing of edge-case JSON |

**Rules:**
- `@Serializable` on every DTO — missing annotation = runtime crash with no compile warning
- `@SerialName("snake_case")` on every field that doesn't match Kotlin camelCase — stable wire format, refactor-safe
- Polymorphic sealed classes: `@SerialName` on each variant (e.g., `@SerialName("jump")` on `MetricPayload.Jump`)
- Custom serializers for `Instant`, `UUID` — put in `commonMain/util/serializers/`

**Common mistake:** `java.util.UUID` in `commonMain`. JVM-only type, crashes on iOS. Use `kotlinx.serialization` custom serializer + `String` representation.

## Cross-References

| File | Covers |
|------|--------|
| [viewmodels.md](viewmodels.md) | ViewModels, coroutines, Flow, state management |
| [expect-actual.md](expect-actual.md) | Platform engine injection, source set rules |
| [data-layer.md](data-layer.md) | multiplatform-settings, Room KMP, token storage |
| [error-handling.md](error-handling.md) | Full `AppError` sealed hierarchy, mapping rules |
| [testing.md](testing.md) | MockEngine, Mokkery, shared test patterns |
| [gradle.md](gradle.md) | Build configuration, dependency versions, source sets |
| [android-ui.md](android-ui.md) | Compose M3, Hilt integration, Android-specific wiring |
| [ios-ui.md](ios-ui.md) | SwiftUI interop, SKIE, lifecycle |

**External skills:**
| Skill | Use for |
|-------|---------|
| `finding-docs` | Ktor API docs, kotlinx-serialization reference |
| `github` | Ktor/KMP compatibility issues, Ktor plugin examples |
| `using-websearch` | Ktor 3.x migration guide, KMP library compatibility matrix |
```

- [ ] **Step 2: Verify networking.md created**

Run: `wc -l ~/.agents/skills/kmp-development/reference/networking.md`
Expected: ~75 lines

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/networking.md
git commit -m "feat(kmp-skill): add networking.md (Ktor, auth, serialization)"
```

### Task 8: Create viewmodels.md (split from shared-code.md)

**Files:**

- Create: `~/.agents/skills/kmp-development/reference/viewmodels.md`

- [ ] **Step 1: Create viewmodels.md with ViewModel + Coroutines + Flow content**

```markdown
# ViewModels, Coroutines & Flow

ViewModel patterns, coroutine scoping, and Flow operators for shared code.

**Topics:** ViewModels | Coroutines | Flow operators | Error propagation | Cross-references

## ViewModels

**Pattern:** `StateFlow<UiState>` for screen state + `SharedFlow<UiAction>` for one-shot events.

**UiState:** Sealed interface with `data class` and `data object` variants. Always immutable. Mutations via `.copy()`. Never `var` fields.

**UiAction:** One-shot events (navigation, toasts) via `SharedFlow` with `extraBufferCapacity = 1`. Emits via `tryEmit()`.

**Lifecycle:** Android uses `viewModelScope` (cancelled in `onCleared`). iOS uses a manual scope cancelled in `deinit` (see [ios-ui.md](ios-ui.md)).

**Common mistakes:**
- `StateFlow` for navigation events — re-consumed on config change. Use `SharedFlow`.
- Exposing `MutableStateFlow` publicly — anyone can write. Use `asStateFlow()`.

## Coroutines

**Dispatcher table:**

| Dispatcher | Use for |
|------------|---------|
| `Dispatchers.Default` | CPU work: JSON parsing, computation |
| `Dispatchers.IO` | Network, files, S3 (Android-only in shared — use `Default` in commonMain) |
| `Dispatchers.Main` | UI updates only |

**Scopes:**
- `viewModelScope` only — never `GlobalScope`
- Set dispatcher at call site, not inside repository

**supervisorScope vs coroutineScope:**

| Scope | Failure behavior | When to use |
|-------|-----------------|-------------|
| `supervisorScope` | One child fails, siblings continue | Independent parallel calls (fetch profile + sessions) |
| `coroutineScope` | One child fails, all cancel | All-or-nothing operations (transaction steps) |

**stateIn/shareIn:** Always `WhileSubscribed(5000)`. The 5s grace period keeps the upstream alive during config changes. `Eagerly` wastes resources; `Lazily` never starts until first collector.

**Common mistake:** `Dispatchers.Main` inside repository. Set the dispatcher at the call site (`viewModelScope.launch(Dispatchers.IO)`), not hardcoded in the repo.

## Flow Operators

- `stateIn` for UI state — converts cold flow to `StateFlow` with an initial value
- `shareIn` for shared streams — multiple subscribers, one upstream subscription
- `combine(flowA, flowB)` for merging — produces a new value when either emits

**WhileSubscribed(5000):** Keeps upstream active for 5 seconds after the last subscriber disappears. Without it, rapid subscribe/unsubscribe cycles (rotation) restart the upstream each time.

**Common mistake:** Nested `collect` — `flowA.collect { flowB.collect { ... } }`. This creates nested suspensions that leak. Use `combine` or `flatMapLatest` instead.

## Error Propagation

**Chain:** `DataSource` (throws platform exceptions) → `Repository` (wraps to `AppError`) → `UseCase` (returns `Result<T, AppError>`) → `ViewModel` (emits `UiState.Error`)

**Repository is the boundary.** No platform exception crosses it. Use `runCatching` at the repository level to wrap all Ktor/network exceptions into `AppError` variants.

**ViewModel receives `Result`, maps to `UiState`:** `.onSuccess { ... } .onFailure { ... }`

**Common mistakes:**
- Letting `ClientRequestException` reach ViewModel — Ktor types leak, couples ViewModel to network layer
- `throw` from repository for expected failures — use `Result.Failure`
- `try/catch` in every API method — use `runCatching` at the repository boundary instead

**Full error hierarchy:** See [error-handling.md](error-handling.md) for the complete `AppError` sealed tree and mapping rules.

## Cross-References

| File | Covers |
|------|--------|
| [networking.md](networking.md) | Ktor client, auth, serialization |
| [expect-actual.md](expect-actual.md) | Platform engine injection, source set rules |
| [data-layer.md](data-layer.md) | multiplatform-settings, Room KMP, token storage |
| [error-handling.md](error-handling.md) | Full `AppError` sealed hierarchy, mapping rules |
| [testing.md](testing.md) | MockEngine, Mokkery, shared test patterns |
| [android-ui.md](android-ui.md) | Compose M3, Hilt ViewModel wiring |
| [ios-ui.md](ios-ui.md) | SwiftUI interop, SKIE, ViewModel deinit |
| [platform-apis.md](platform-apis.md) | CameraX, BLE (Kable), WorkManager |

**External skills:**
| Skill | Use for |
|-------|---------|
| `finding-docs` | Coroutines guide, Flow API reference, StateFlow docs |
| `github` | Coroutines/KMP compatibility issues |
| `using-websearch` | Kotlin Flow best practices, WhileSubscribed patterns |
```

- [ ] **Step 2: Verify viewmodels.md created**

Run: `wc -l ~/.agents/skills/kmp-development/reference/viewmodels.md`
Expected: ~75 lines

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/viewmodels.md
git commit -m "feat(kmp-skill): add viewmodels.md (ViewModels, coroutines, Flow)"
```

### Task 9: Rewrite shared-code.md as redirect hub

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/shared-code.md`

- [ ] **Step 1: Replace shared-code.md content with redirect to networking.md + viewmodels.md**

Write the entire file:

```markdown
# Shared Code (commonMain)

This reference has been split into two focused files for better depth:

- **[networking.md](networking.md)** — Ktor client, auth interceptors, serialization
- **[viewmodels.md](viewmodels.md)** — ViewModels, coroutines, Flow, state management

Use the `feature` command to load both sequentially for full-stack feature creation.

## Quick Reference (common patterns)

| Pattern | Where | Reference |
|---------|-------|-----------|
| Ktor client setup | commonMain | [networking.md](networking.md) |
| Auth / token refresh | commonMain | [networking.md](networking.md) |
| Serialization config | commonMain | [networking.md](networking.md) |
| ViewModel pattern | commonMain | [viewmodels.md](viewmodels.md) |
| Dispatcher choice | commonMain | [viewmodels.md](viewmodels.md) |
| Flow operators | commonMain | [viewmodels.md](viewmodels.md) |
| Error propagation chain | commonMain → ViewModel | [viewmodels.md](viewmodels.md) + [error-handling.md](error-handling.md) |

## Cross-References

| File | Covers |
|------|--------|
| [networking.md](networking.md) | Ktor, auth, serialization |
| [viewmodels.md](viewmodels.md) | ViewModels, coroutines, Flow |
| [expect-actual.md](expect-actual.md) | Platform engine injection, source set rules |
| [data-layer.md](data-layer.md) | multiplatform-settings, Room KMP, token storage |
| [error-handling.md](error-handling.md) | Full `AppError` sealed hierarchy, mapping rules |
| [testing.md](testing.md) | MockEngine, Mokkery, shared test patterns |
| [android-ui.md](android-ui.md) | Compose M3, Hilt integration, Android-specific wiring |
| [ios-ui.md](ios-ui.md) | SwiftUI interop, SKIE, lifecycle |
| [gradle.md](gradle.md) | Build configuration, dependency versions, source sets |
```

- [ ] **Step 2: Verify shared-code.md is now a redirect hub**

Run: `grep -c "networking.md\|viewmodels.md" ~/.agents/skills/kmp-development/reference/shared-code.md`
Expected: 6+ hits

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/shared-code.md
git commit -m "refactor(kmp-skill): shared-code.md → redirect hub to networking.md + viewmodels.md"
```

### Task 10: Update INDEX.md for new files

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/INDEX.md`

- [ ] **Step 1: Add networking.md and viewmodels.md rows, update shared-code.md description**

Replace the first row in the table:

```markdown
| [shared-code.md](shared-code.md) | Code | commonMain business logic | Ktor client, auth interceptors, serialization, ViewModels, coroutines, Flow, error propagation |
```

With:

```markdown
| [shared-code.md](shared-code.md) | Code | Redirect hub → networking + viewmodels | Links to networking.md and viewmodels.md |
| [networking.md](networking.md) | Code | Networking | Ktor client, auth interceptors, serialization |
| [viewmodels.md](viewmodels.md) | Code | State management | ViewModels, coroutines, Flow operators, error propagation |
```

- [ ] **Step 2: Update cross-cutting concerns table**

In the cross-cutting concerns table, replace all `shared-code.md` references:

Replace:

```markdown
| Error handling | error-handling.md | shared-code.md (propagation), data-layer.md (storage errors) |
| Offline-first | data-layer.md | shared-code.md (coroutine scopes), platform-apis.md (WorkManager) |
| Platform boundary | expect-actual.md | shared-code.md (factory DI), ios-ui.md (SKIE), android-ui.md (Hilt) |
```

With:

```markdown
| Error handling | error-handling.md | viewmodels.md (propagation), data-layer.md (storage errors) |
| Offline-first | data-layer.md | viewmodels.md (coroutine scopes), platform-apis.md (WorkManager) |
| Platform boundary | expect-actual.md | networking.md (factory DI), ios-ui.md (SKIE), android-ui.md (Hilt) |
```

- [ ] **Step 3: Verify INDEX.md updated**

Run: `grep "networking.md\|viewmodels.md" ~/.agents/skills/kmp-development/reference/INDEX.md`
Expected: 3+ hits each

- [ ] **Step 4: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/INDEX.md
git commit -m "feat(kmp-skill): update INDEX.md with networking.md + viewmodels.md"
```

---

## Wave 4 — P1 Cross-References & Formatting

### Task 11: Add cross-references to compose-multiplatform.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/compose-multiplatform.md:122-137`

- [ ] **Step 1: Expand the Internal cross-references table**

Replace the internal cross-references table (lines 124-132):

```markdown
| File | Covers |
|------|--------|
| [android-ui.md](android-ui.md) | Android-only Compose M3, Hilt, CameraX wiring, WorkManager |
| [ios-ui.md](ios-ui.md) | SwiftUI, SKIE, XCFramework, Keychain, ViewModel lifecycle |
| [expect-actual.md](expect-actual.md) | Interface vs expect/actual decision, source set hierarchy |
| [shared-code.md](shared-code.md) | ViewModels, Ktor client, serialization, coroutines |
| [testing.md](testing.md) | commonTest patterns, Mokkery, MockEngine |
| [gradle.md](gradle.md) | CMP version catalog, source sets, SKIE plugin config |
```

With:

```markdown
| File | Covers |
|------|--------|
| [android-ui.md](android-ui.md) | Android-only Compose M3, Hilt, CameraX wiring, WorkManager |
| [ios-ui.md](ios-ui.md) | SwiftUI, SKIE, XCFramework, Keychain, ViewModel lifecycle |
| [expect-actual.md](expect-actual.md) | Interface vs expect/actual decision, source set hierarchy |
| [viewmodels.md](viewmodels.md) | ViewModels, coroutines, Flow — shared state patterns for Compose |
| [networking.md](networking.md) | Ktor client, auth — data fetching in shared Compose screens |
| [testing.md](testing.md) | commonTest patterns, Mokkery, MockEngine, Compose UI testing |
| [gradle.md](gradle.md) | CMP version catalog, source sets, SKIE plugin config |
| [data-layer.md](data-layer.md) | Repository pattern, offline-first — Compose observes Flow from repo |
| [error-handling.md](error-handling.md) | Error-to-UiState mapping — Compose error screens |
| [shared-code.md](shared-code.md) | Redirect hub to networking.md + viewmodels.md |
```

- [ ] **Step 2: Verify compose-multiplatform.md has 10 inbound cross-refs**

Run: `grep -c "\.md" ~/.agents/skills/kmp-development/reference/compose-multiplatform.md`
Expected: 10+ cross-reference links

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/compose-multiplatform.md
git commit -m "feat(kmp-skill): add cross-refs to compose-multiplatform.md (10 files)"
```

### Task 12: Fix ios-ui.md link format

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/ios-ui.md:162-175`

- [ ] **Step 1: Convert backtick links to markdown format in cross-references table**

Replace lines 165-175:

```markdown
| `android-ui.md` | Compose M3, Hilt, Navigation, CameraX — Android counterpart |
| `data-layer.md` | Room KMP, multiplatform-settings, repository pattern, token storage, Keychain typed wrappers |
| `error-handling.md` | Sealed error hierarchy, Result types, cross-platform propagation |
| `expect-actual.md` | expect/actual boundaries, interface vs expect/actual decision guide |
| `gradle.md` | Version catalog, multiplatform config, SKIE version compatibility |
| `platform-apis.md` | BLE (Kable), Camera, WorkManager, sensors — device-level APIs |
| `shared-code.md` | ViewModels, Ktor, serialization, coroutines in commonMain |
| `testing.md` | commonTest, Mokkery, Ktor MockEngine, ViewModel testing, platform runners |
```

With:

```markdown
| [android-ui.md](android-ui.md) | Compose M3, Hilt, Navigation, CameraX — Android counterpart |
| [data-layer.md](data-layer.md) | Room KMP, multiplatform-settings, repository pattern, token storage, Keychain typed wrappers |
| [error-handling.md](error-handling.md) | Sealed error hierarchy, Result types, cross-platform propagation |
| [expect-actual.md](expect-actual.md) | expect/actual boundaries, interface vs expect/actual decision guide |
| [gradle.md](gradle.md) | Version catalog, multiplatform config, SKIE version compatibility |
| [platform-apis.md](platform-apis.md) | BLE (Kable), Camera, WorkManager, sensors — device-level APIs |
| [viewmodels.md](viewmodels.md) | ViewModels, coroutines, Flow in commonMain |
| [networking.md](networking.md) | Ktor client, auth, serialization in commonMain |
| [testing.md](testing.md) | commonTest, Mokkery, Ktor MockEngine, ViewModel testing, platform runners |
```

- [ ] **Step 2: Verify no backtick-format links remain**

Run: `grep '| \`.*\.md\`' ~/.agents/skills/kmp-development/reference/ios-ui.md`
Expected: zero hits

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/ios-ui.md
git commit -m "fix(kmp-skill): convert ios-ui.md backtick links to markdown format"
```

---

## Wave 5 — P1 Content Additions

### Task 13: Add CI/CD section to gradle.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/gradle.md:100-121`

- [ ] **Step 1: Add CI/CD section before Cross-References**

Insert after line 100 (after Build Performance section), before Cross-References:

```markdown
## CI/CD for KMP

**GitHub Actions matrix** — run all target tests in CI:

| Job | Command | Runner |
|-----|---------|--------|
| JVM tests | `./gradlew :shared:jvmTest` | `ubuntu-latest` |
| Android instrumented | `./gradlew :androidApp:connectedDebugAndroidTest` | `macos-latest` (emulator) |
| iOS simulator | `./gradlew :shared:iosSimulatorArm64Test` | `macos-latest` |
| Android lint | `./gradlew :androidApp:lintDebug` | `ubuntu-latest` |

**Gradle caching in CI:**
```yaml
- uses: actions/setup-java@v4
  with: { distribution: temurin, java-version: 21 }
- uses: gradle/actions/setup-gradle@v4
  with:
    cache-read-only: ${{ github.ref != 'refs/heads/master' }}
    gradle-home-cache-includes: |
      caches
      notifications
      wrapper/dists
```

**SKIE build requirements:** Pin Xcode version in CI — SKIE framework build depends on Xcode SDK. Specify `macos-14` runner (Xcode 15.3+) for `iosSimulatorArm64Test`.

**Test parallelism:** `./gradlew :shared:allTests --parallel` runs platform test tasks concurrently. Add `--max-workers=4` to limit worker count on CI.

**Sharding (large test suites):** `./gradlew test -Pandroid.testInstrumentationRunnerArguments.numShards=4 -Pandroid.testInstrumentationRunnerArguments.shardIndex=$SHARD`

**Common mistake:** Running `jvmTest` only in CI and skipping iOS tests. Native issues surface only on `iosSimulatorArm64Test`.
```

- [ ] **Step 2: Add version freshness note to Version Catalog section**

After line 19 (after the version table), add:

```markdown
**Note:** Versions above are project-pinned, not latest stable. Check compatibility matrix before updating. Current latest: Kotlin 2.3.21, Ktor 3.5.0, Hilt 2.59.2.
```

- [ ] **Step 3: Verify CI/CD section exists**

Run: `grep -n "CI/CD" ~/.agents/skills/kmp-development/reference/gradle.md`
Expected: 1+ hit

- [ ] **Step 4: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/gradle.md
git commit -m "feat(kmp-skill): add CI/CD section and version freshness note to gradle.md"
```

### Task 14: Add CMP 1.11.0 breaking changes to compose-multiplatform.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/compose-multiplatform.md:9-14`

- [ ] **Step 1: Add CMP 1.11.0 breaking changes after version requirements section**

After line 14 ("CMP tracks Jetpack Compose: 1.11.x ≈ Jetpack 1.10.x"), insert:

```markdown
**CMP 1.11.0 breaking changes:**
- Shader wrapper API changed — verify custom `RenderEffect` usage
- Dropped x86_64 Android emulator support (arm64 only)
- `WebElementView` renamed to `HtmlElementView` — update imports
- `parallelRendering` enabled by default — may affect custom layout performance
- `ComposeUIView` new API replaces older `ComposeUIViewController` patterns on iOS
- Native iOS text input (experimental) — `UIKitTextField` for native keyboard behavior

**CMP 1.11.0 Kotlin for JS/Wasm:** Requires Kotlin 2.3.20+ (not just 2.3).
```

- [ ] **Step 2: Add Wasm/web target section**

After the Minimum targets line (line 18), insert:

```markdown
**Wasm/web target:** Beta status. `HtmlElementView` for DOM interop. Limited to Kotlin/JS subset. Not production-ready for full web apps.
```

- [ ] **Step 3: Verify breaking changes are documented**

Run: `grep -c "1.11.0" ~/.agents/skills/kmp-development/reference/compose-multiplatform.md`
Expected: 4+ hits (version line + breaking changes)

- [ ] **Step 4: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/compose-multiplatform.md
git commit -m "feat(kmp-skill): add CMP 1.11.0 breaking changes and Wasm/web section"
```

### Task 15: Expand Navigation section in android-ui.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/android-ui.md:52-60`

- [ ] **Step 1: Expand Navigation Compose section**

Replace lines 52-59:

```markdown
## Navigation Compose

**Type-safe routes**: Use `@Serializable` data class (with args) or data object (no args). Navigation 2.8+ supports this natively. Define all routes in a single `Routes.kt`.

**Wiring**: `composable<RouteType> { entry -> val route = entry.toRoute<RouteType>() }` inside `NavHost`. Never use string-based routes.

**What to check**: grep for `navigate("` -- any string-literal route is a typo waiting to happen. All routes must be `@Serializable` classes.
```

With:

```markdown
## Navigation Compose

**Type-safe routes**: Use `@Serializable` data class (with args) or data object (no args). Navigation 2.8+ supports this natively. Define all routes in a single `Routes.kt`.

**Deep links**: Add `deepLinks` parameter to `composable<RouteType>`: `deepLinks = listOf(navDeepLink { uriPattern = "skatelab://session/{id}" })`. Test with `adb shell am start -a android.intent.action.VIEW -d "skatelab://session/123"`.

**Process death restoration**: `SavedStateHandle` in ViewModel restores route args after process death. Navigation state auto-saves via `NavHost`. Do not store nav state in ViewModel manually.

**Nested graphs / bottom nav**: Use `navigation<RouteType>(startDestination)` inside `NavHost` for feature-scoped graphs. Bottom nav switches between top-level navigation graphs. Each tab maintains its own back stack.

**Predictive back**: Enable with `predictiveBack = true` on `NavHost`. Requires API 33+ for full animation; gracefully degrades on older versions.

**Wiring**: `composable<RouteType> { entry -> val route = entry.toRoute<RouteType>() }` inside `NavHost`. Never use string-based routes.

**What to check**: grep for `navigate("` -- any string-literal route is a typo waiting to happen. All routes must be `@Serializable` classes.
```

- [ ] **Step 2: Verify navigation section expanded**

Run: `grep -c "deep link\|process death\|nested\|predictive" ~/.agents/skills/kmp-development/reference/android-ui.md`
Expected: 4+ hits

- [ ] **Step 3: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/android-ui.md
git commit -m "feat(kmp-skill): expand Navigation section in android-ui.md (deep links, process death, nested graphs)"
```

---

## Wave 6 — Update SKILL.md Commands Table

### Task 16: Update SKILL.md commands table for file split

**Files:**

- Modify: `~/.agents/skills/kmp-development/SKILL.md:43`

- [ ] **Step 1: Replace `shared` command row with two rows**

Replace line 43:

```markdown
| `shared` | Code | Networking, auth, ViewModels, Flow, coroutines | [reference/shared-code.md](reference/shared-code.md) |
```

With:

```markdown
| `shared` | Code | Redirect hub → networking + viewmodels | [reference/shared-code.md](reference/shared-code.md) |
| `net` | Code | Ktor client, auth, serialization | [reference/networking.md](reference/networking.md) |
| `vm` | Code | ViewModels, coroutines, Flow, state management | [reference/viewmodels.md](reference/viewmodels.md) |
```

- [ ] **Step 2: Update routing rule for `shared` command**

Update routing rule 1 (line 61):

Replace:

```markdown
1. **No argument**: load SKILL.md + `shared-code.md` (default entry)
```

With:

```markdown
1. **No argument**: load SKILL.md + `networking.md` (default entry)
2. **`shared` command**: load `shared-code.md` (redirect hub → `networking.md` + `viewmodels.md`)
```

Renumber existing rules 2-7 to 3-8.

- [ ] **Step 3: Verify commands table has new entries**

Run: `grep "net\|vm\|feature" ~/.agents/skills/kmp-development/SKILL.md | head -5`
Expected: `net`, `vm`, `feature` command rows

- [ ] **Step 4: Commit**

```bash
git add ~/.agents/skills/kmp-development/SKILL.md
git commit -m "feat(kmp-skill): add net/vm/feature commands, update routing rules"
```

---

## Wave 7 — Update All Cross-References

### Task 17: Update cross-references in all reference files for networking.md + viewmodels.md

**Files:**

- Modify: `~/.agents/skills/kmp-development/reference/expect-actual.md`
- Modify: `~/.agents/skills/kmp-development/reference/data-layer.md`
- Modify: `~/.agents/skills/kmp-development/reference/error-handling.md`
- Modify: `~/.agents/skills/kmp-development/reference/testing.md`
- Modify: `~/.agents/skills/kmp-development/reference/platform-apis.md`

- [ ] **Step 1: Update expect-actual.md cross-refs**

In the cross-references table, replace the `shared-code.md` row:

```markdown
| [shared-code.md](shared-code.md) | Ktor client, serialization, ViewModels, coroutines, error chains |
```

With:

```markdown
| [networking.md](networking.md) | Ktor client, serialization, auth |
| [viewmodels.md](viewmodels.md) | ViewModels, coroutines, error chains |
```

- [ ] **Step 2: Update data-layer.md cross-refs**

Replace the `shared-code.md` row in internal cross-refs:

```markdown
- [shared-code.md](shared-code.md) -- ViewModels, Ktor client, serialization, auth interceptor
```

With:

```markdown
- [networking.md](networking.md) -- Ktor client, serialization, auth interceptor
- [viewmodels.md](viewmodels.md) -- ViewModels, coroutines, Flow
```

- [ ] **Step 3: Update error-handling.md cross-refs**

Replace the `shared-code.md` row:

```markdown
- [shared-code.md](shared-code.md) — ViewModels, Ktor client, serialization, coroutine patterns in commonMain
```

With:

```markdown
- [networking.md](networking.md) — Ktor client, serialization, auth patterns in commonMain
- [viewmodels.md](viewmodels.md) — ViewModels, coroutine patterns, Flow in commonMain
```

- [ ] **Step 4: Update testing.md cross-refs**

Replace the `shared-code.md` row:

```markdown
- [shared-code.md](shared-code.md) -- commonMain architecture, expect/actual boundaries
```

With:

```markdown
- [networking.md](networking.md) -- Ktor client, serialization, networking test patterns
- [viewmodels.md](viewmodels.md) -- ViewModels, coroutines, ViewModel test patterns
```

- [ ] **Step 5: Update platform-apis.md cross-refs**

If platform-apis.md has a `shared-code.md` cross-reference, replace similarly.

- [ ] **Step 6: Verify all cross-refs updated**

Run: `grep -rn "shared-code.md" ~/.agents/skills/kmp-development/reference/ --include="*.md"`
Expected: only in shared-code.md itself (redirect hub) and INDEX.md (redirect entry)

- [ ] **Step 7: Commit**

```bash
git add ~/.agents/skills/kmp-development/reference/
git commit -m "refactor(kmp-skill): update all cross-refs for networking.md + viewmodels.md split"
```

---

## Verification

After all tasks complete, run a final consistency check:

- [ ] **Cross-reference audit:** `grep -rn "shared-code.md" ~/.agents/skills/kmp-development/ --include="*.md"` — should only appear in shared-code.md (redirect) and INDEX.md (redirect row)
- [ ] **Navigation 3 audit:** `grep -rn "navigation-compose3\|navigation-compose 3" ~/.agents/skills/kmp-development/` — zero hits
- [ ] **Backtick link audit:** `grep -rn '| \`.*\.md\` |' ~/.agents/skills/kmp-development/reference/` — zero hits
- [ ] **Law #6 audit:** `grep -n "Law 6\|law #6\|6\." ~/.agents/skills/kmp-development/SKILL.md` — should mention `androidApp`
- [ ] **New commands audit:** `grep "net\|vm\|feature" ~/.agents/skills/kmp-development/SKILL.md` — all three present
- [ ] **New bans audit:** `grep -c "runBlocking\|java.util.UUID\|@Parcelize" ~/.agents/skills/kmp-development/SKILL.md` — 3+ hits each
