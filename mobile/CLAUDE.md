# mobile/CLAUDE.md

## Overview

Kotlin Multiplatform app: shared logic (auth, API, models) + native UI per platform.
- **Android**: Jetpack Compose + Material 3 — реализовано
- **iOS**: SwiftUI — планируется в ближайшем будущем

Shared модуль avoids code duplication. UI нативный на каждой платформе. Design system единая с frontend.

## History

Flutter → native Kotlin (05-09) → KMP shared module (05-22). Camera2 removed early — recording via CameraX only.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Shared** | KMP, kotlinx-serialization, Ktor, kotlinx-datetime |
| **Android UI** | Jetpack Compose, Material 3, Navigation Compose |
| **iOS UI** | SwiftUI (planned) |
| **DI** | Hilt (KSP) |
| **Network** | Ktor (OkHttp Android, Darwin iOS) |
| **BLE** | Kable (WT901 IMU sensors) |
| **DB** | Room (Android, cached sessions + pending uploads) |
| **Camera** | CameraX (video recording) |
| **Video playback** | Media3 ExoPlayer |
| **Charts** | Vico (Compose + Material 3) |
| **Background** | WorkManager (chunked upload), Foreground Service (sensor recording) |
| **Protobuf** | protobuf-javalite (IMU data serialization) |
| **Testing** | kotlin-test, coroutines-test, Mokkery (commonTest), Turbine, Kover |
| **Lint** | ktlint |
| **Build** | Gradle + build-logic conventions, configuration cache, KSP isolation |

Min SDK 24, Target SDK 35, Compose BOM managed.

## Project Structure

```
mobile/
├── shared/                        # KMP shared module
│   └── src/
│       ├── commonMain/             # API client, auth, models (shared Android+iOS)
│       │   └── ru/skatelab/shared/
│       │       ├── api/            # SkateLabClient, AuthApi, SessionsApi, UploadsApi, UsersApi, ProcessApi
│       │       ├── auth/          # AuthRepository, TokenStorage (multiplatform-settings)
│       │       ├── models/        # TokenResponse, SessionResponse, UserResponse, etc.
│       │       └── state/         # AuthViewModel, SessionsViewModel, ProcessingViewModel
│       ├── commonTest/            # Shared tests (AuthApi, AuthRepository, Serialization)
│       ├── androidMain/           # Android-specific: OkHttp engine, AndroidTokenStorage
│       └── iosMain/               # iOS-specific: Darwin engine, IosTokenStorage
├── androidApp/                    # Android app (92 source files)
│   └── src/main/java/ru/skatelab/capture/
│       ├── App.kt                 # Hilt application
│       ├── MainActivity.kt
│       ├── di/                    # Hilt modules: AppModule, CameraModule, DatabaseModule
│       ├── navigation/            # Routes
│       ├── domain/                # Clean Architecture domain layer
│       │   ├── model/            # CalibrationData, CaptureSession, ImuSample, SensorInfo
│       │   ├── repository/       # BleRepository, CameraRepository, SessionRepository (interfaces)
│       │   ├── service/          # ImuCollector, Logger, SessionExporter, TimeSynchronizer (interfaces)
│       │   └── usecase/          # 12 use cases (Connect, Calibrate, Record, Export, etc.)
│       ├── data/                  # Implementations
│       │   ├── ble/              # BleManager, KableBleRepository, Wt901Parser, Wt901Commander
│       │   ├── camera/           # CameraXRecorder, CameraRepositoryImpl
│       │   ├── db/               # Room: AppDatabase, CachedSessionDao, PendingUploadDao
│       │   ├── export/           # ImuStreamWriter, ManifestBuilder, ZipExporter
│       │   ├── imu/              # ImuParser
│       │   ├── recording/        # ImuCollector (implementation)
│       │   ├── repository/       # SessionRepositoryImpl
│       │   ├── share/            # ShareManager
│       │   └── sync/             # TimeSyncManager, TimeSynchronizerImpl, PeriodicTimeSync
│       ├── presentation/          # Feature screens + ViewModels
│       │   ├── ble/              # BleScanScreen + ViewModel
│       │   ├── calibration/      # CalibrationScreen + ViewModel (Markley eigendecomposition)
│       │   ├── recording/        # RecordingScreen + ViewModel
│       │   ├── session/          # SessionListScreen + ViewModel
│       │   ├── sessiondetail/    # SessionDetailScreen + ViewModel (ExoPlayer + IMU charts)
│       │   ├── export/           # ExportScreen + ViewModel
│       │   └── theme/            # SkateLab theme (Inter Variable, OKLCH colors, unified design system)
│       ├── ui/                    # Android-specific UI components (auth, camera, profile, tabs)
│       ├── service/               # SensorRecordingService (foreground)
│       └── upload/                # ChunkedUploader, UploadScheduler, UploadWorker
├── proto/                         # Protobuf definitions
├── build-logic/                   # Gradle convention plugins
└── scripts/                      # Build scripts
```

## Architecture

Clean Architecture: **presentation** → **domain** → **data**

- domain/ содержит interfaces (repository, service) + models + use cases
- data/ содержит implementations
- presentation/ содержит Compose screens + ViewModels (StateFlow)

Shared module: API client + auth + models — переиспользуется Android и iOS.

## Key Flows

- **BLE**: Kable → Wt901Parser → ImuCollector → foreground service
- **Recording**: CameraX video + BLE IMU simultaneously, time-synced via TimeSynchronizerImpl
- **Upload**: ChunkedUploader → UploadWorker (WorkManager, retry on failure)
- **Calibration**: Markley eigendecomposition + tightened thresholds
- **Session viewer**: ExoPlayer video + Vico IMU charts + playhead sync

## Design System

Unified with frontend: OKLCH colors, Inter Variable font, same border-radius tokens. Style Dictionary generates CSS/Android/iOS tokens.

## Build & Local Run

Debug APK для прогона в эмуляторе собираем локально (машина 62 Gi RAM). Прямой путь `./gradlew :androidApp:assembleDebug` обычно работает, но локальный Gradle daemon нестабилен — периодически падает (OOM / порт-конфликты). Если прямой вызов упал, используй Docker-контейнер (ниже). Release и CI-верификацию — на GitHub Actions.

```bash
cd mobile
./gradlew :androidApp:assembleDebug     # → androidApp/build/outputs/apk/debug/androidApp-debug.apk
./gradlew :androidApp:assembleRelease    # нужен signing config
./gradlew :androidApp:lint                # android lint
./gradlew :androidApp:test                # unit-тесты
```

### Сборка APK через Docker-контейнер (fallback при падении daemon'а)

Когда локальный Gradle daemon падает (OOM / порт-конфликты) — собирай через Docker-образ `android-apk-builder:local` (JDK 17 + Android SDK 35), `--no-daemon`:

```bash
docker run --rm -v "$(pwd)/..:/work" -w /work/mobile android-apk-builder:local \
  bash -c 'chmod +x gradlew && ./gradlew :androidApp:assembleDebug --no-daemon --no-configuration-cache'
```

Docker создаёт build-файлы с правами root — `rm -rf shared/build androidApp/build` с хоста не работает. Очистка:

```bash
docker run --rm -v "$(pwd)/..:/work" android-apk-builder:local rm -rf /work/mobile/shared/build /work/mobile/androidApp/build
```

### ⚠️ Проверяй md5 после сборки

**ВСЕГДА** проверяй md5 APK после сборки и перед отправкой/установкой. Gradle может **не пересобрать** APK при ошибке компиляции (`BUILD FAILED`), но старый APK остаётся в `build/outputs/apk/`. Несколько раз отправляли старый APK, не заметив что пересборка не произошла.

```bash
md5sum androidApp/build/outputs/apk/debug/androidApp-debug.apk   # сравни с предыдущим — должен отличаться
```

Также проверяй `BUILD SUCCESSFUL` в выводе — не `BUILD FAILED`. Если FAILED — читай `e: file://...` строки (ошибки компиляции Kotlin).

### Ktor 3.x: response.request — функция, не property

В Ktor 3.x `HttpResponse.request` — это **функция** (invoke), не property. `response.request.url` в некоторых контекстах вызывает `Function invocation 'request(...)' expected`. Избегай прямого доступа к `response.request` в println/строках — используй `response.status` только.

GitHub Actions — `mobile.yml` (path-filtered): shared tests, Android lint/test, debug APK build, тирья lint/test/build. Код-чеки (ktlint, android lint, unit/Android tests, iOS tests) должны быть зелёными до мёрджа — часть `finishing-a-development-branch`.

## Docker-эмулятор (основной способ прогона)

Эмулятор **в контейнере**, не на хосте. Хостовый ADB конфликтует по порту 5037/правам — не используем. Всё через `docker exec skatelab-emulator ...`.

- Образ `budtmo/docker-android:emulator_14.0` (Android 14, API 34), требует KVM (`/dev/kvm`).
- Контейнер `skatelab-emulator`, управляется systemd-юнитом `skatelab-emulator.service` (compose + юнит в `mobile/e2e/systemd/`).
- Healthcheck: `adb shell getprop sys.boot_completed` → `1`.
- Maestro CLI стоит **внутри** контейнера: `/home/androidusr/.maestro/bin/maestro`.

### Жизненный цикл

```bash
# Один раз (ставит Maestro CLI, gh, копирует compose/flows, стартует эмулятор):
cd mobile/e2e && ./setup-emulator.sh

# Дальше под systemd:
systemctl status | start | stop skatelab-emulator.service
```

### Второй эмулятор для параллельных прогонов (два тестировщика)

Если два человека гоняют Maestro-флоу одновременно на одном хосте — единственный `skatelab-emulator` даёт конфликты (dADB, driver, порт 5554). Подними второй изолированный контейнер:

```bash
docker run -d --name skatelab-emulator-2 --device /dev/kvm \
  -p 127.0.0.1:5556:5554 -p 127.0.0.1:5557:5555 \
  -e EMULATOR_FLAGS="-no-window -no-audio -no-boot-anim -gpu swiftshader_indirect -memory 2048 -netfast -accel on -partition-size 1024 -no-snapshot-save" \
  -e DATAPARTITION="1024m" --tmpfs /data:size=2G \
  -v skatelab_emulator2_data:/root/.android --cpus=4 --memory=16G --restart=unless-stopped \
  budtmo/docker-android:emulator_14.0
```

**Грабли второго эмулятора (важно):**
- **НЕ** передавай `-port 5556` в `EMULATOR_FLAGS` — `budtmo/docker-android` v3.4.2 жёстко проверяет `emulator-5554` для boot; кастомный порт ломает boot-check (`RuntimeError: booted is checked 59 times`). Эмулятор внутри **обоих** контейнеров остаётся `emulator-5554`; изоляция — через remap хост-портов (`5556:5554`, `5557:5555`), у каждого контейнера своё adb-пространство.
- **Boot МЕДЛЕННЫЙ (~8 мин)** когда два эмулятора делят `/dev/kvm` (`-accel on` + swiftshader software-render). supervisord-процесс `device` сдаётся через ~2 мин (`RuntimeError: booted is checked 59 times!`), но **QEMU продолжает работать** и `sys.boot_completed` становится `1` позже (~8 мин). RuntimeError supervisord игнорируй — полли `adb shell getprop sys.boot_completed` напрямую.
- После boot: `adb shell svc wifi enable` + ~12s (свежий эмулятор без сети; проверка `ping 8.8.8.8`).
- Maestro CLI не персистится между рестартами — ставь в контейнер (`wget maestro.zip` → `/home/androidusr/.maestro`), см. memory `second-android-emulator-setup`.
- Прогон на втором эмуляторе: `docker exec -e HOME=/home/androidusr -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin skatelab-emulator-2 maestro test --device emulator-5554 /home/androidusr/flows/<flow>.yaml`.

### Подготовка перед прогоном (после рестарта контейнера)

```bash
docker exec skatelab-emulator adb shell getprop sys.boot_completed                        # дождаться "1"
docker exec skatelab-emulator adb shell service call locale 3 s16 ru.skatelab.capture s16 en-US  # локаль en-US для Maestro-селекторов
docker exec skatelab-emulator adb shell svc wifi enable                                     # WiFi (после рестарта сбрасывается)
# ВСЕ dangerous-разрешения после pm clear (одно CAMERA недостаточно — иначе BLE "nearby devices" dialog блокирует flow):
for p in android.permission.CAMERA android.permission.BLUETOOTH_SCAN android.permission.BLUETOOTH_CONNECT; do
  docker exec skatelab-emulator adb shell pm grant ru.skatelab.capture $p
done
```

### Установка APK в эмулятор

```bash
docker cp androidApp/build/outputs/apk/debug/androidApp-debug.apk skatelab-emulator:/tmp/app-debug.apk
docker exec skatelab-emulator adb install -r /tmp/app-debug.apk
# Или из CI: mobile/e2e/run-e2e.sh --gh-run-id <run-id>  (тянет артефакт apk-debug)
```

## Maestro E2E

Флоу: `mobile/e2e/maestro/flows/` — login, register, logout, tab-navigation, recording, upload-pipeline, session-detail, session-results, upload-queue, upload-processing-check, upload-network-error, processing-stages, gallery-upload.

Скрипт `mobile/e2e/run-e2e.sh` прогоняет весь suite с retry-логикой и пишет JUnit XML в `/opt/skatelab-e2e/reports/`:
```bash
./run-e2e.sh --gh-run-id 12345         # скачать APK из CI и прогнать
./run-e2e.sh --apk-path /tmp/app-debug.apk
```

Один флоу вручную:
```bash
docker exec -e HOME=/home/androidusr \
  -e PATH=/home/androidusr/.maestro/bin:/usr/bin:/bin \
  skatelab-emulator \
  maestro test --device emulator-5554 /home/androidusr/flows/login.yaml
```

Перед копированием флоу в контейнер: `docker cp mobile/e2e/maestro/flows/. skatelab-emulator:/home/androidusr/flows/`

**Тестовый аккаунт** (создан в backend, `is_verified=true`, живой на `api.skatelab.ru`): `test@skatelab.ru` / `Test123456`. login/register проходят против реального API.

### Грабли Maestro 2.6.x (зашито в скрипты, но помнить)
- **dADB-флакинг** (Maestro #1853): первая сессия ок, последующие `AndroidDriverTimeoutException`. Обход — retry: сначала `--no-reinstall-driver`, потом полный реинсталл драйвера. **Никогда** `pm clear` — убивает драйвер APK.
- **Compose `testTag`** невидим для UI Automator → селекторы **по видимому тексту** (`"Email"`, `"Password"`, `"Log in"`), не по `testTag`/`contentDescription`.
- **Мягкая клавиатура** перекрывает тапы → после каждого `inputText` делать `back`, потом тап по следующему полю.
- Перед login-флоу: `adb shell pm clear ru.skatelab.capture` (чистый логин), заново грант **все** dangerous-разрешения (CAMERA + BLUETOOTH_SCAN + BLUETOOTH_CONNECT — `pm clear` сбрасывает гранты; одно CAMERA недостаточно, иначе BLE "find nearby devices" dialog блокирует flow и login падает с "Network error").
- **`addMedia`** резолвит `./assets/...` **относительно flow-файла**, не CWD. Assets должны лежать рядом с flow: `/home/androidusr/flows/assets/` (а не только `/home/androidusr/assets/`). Иначе `Media File Not Found` при одиночном прогоне flow. В `flows/` (UID 1002) для mkdir используй `docker exec -u 0` или `docker cp` напрямую.
- **Airplane-mode тогглинг** (Maestro `setAirplaneMode`) может сбросить WiFi эмулятора. Если login показывает "Network error. Check your connection." mid-suite — `adb shell svc wifi enable` + проверить `settings get global wifi_on` (= 2).

## Ручное тыканье (ADB)

Для UI-автоматации по подключённому ADB — навык `adb-device-testing`. Через контейнер:
```bash
# Запустить приложение
docker exec skatelab-emulator adb shell am start -n ru.skatelab.capture/.MainActivity

# Скриншот — основной «глаз»: прочитать как картинку (Read /tmp/shot.png)
docker exec skatelab-emulator adb shell screencap -p /sdcard/shot.png
docker cp skatelab-emulator:/sdcard/shot.png /tmp/shot.png

# Логи / краши
docker exec skatelab-emulator adb logcat -d -t 200 | grep -iE 'skatelab|AndroidRuntime|FATAL'

# Ввод текста / тапы (когда Maestro избыточен)
docker exec skatelab-emulator adb shell input text "test@skatelab.ru"
docker exec skatelab-emulator adb shell input tap <x> <y>
```

Скриншоты — основной способ увидеть состояние UI. Воспроизводимые сценарии → Maestro-flow (не ручные тыки).

## Before Committing

1. **Lint**: `./gradlew ktlintCheck`
2. **Tests**: `./gradlew testDebugUnitTest`
3. **Build verification**: push to PR — GitHub Actions runs full build + APK assembly

## Документация

- `docs/specs/2026-06-11-e2e-testing-design.md` — дизайн E2E
- `docs/specs/2026-06-11-e2e-testing-research-report.md` — ресёрч E2E
- `docs/plans/2026-05-28-e2e-maestro.md` — план реализации E2E
- `mobile/e2e/maestro/assets/README.md`, `mobile/e2e/maestro/resources/README.md`