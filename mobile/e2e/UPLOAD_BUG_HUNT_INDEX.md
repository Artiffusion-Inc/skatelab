# E2E Bug-Hunt Index — upload on network breaks

Bug-hunt E2E-набор гоняет upload-pipeline против реального backend `api.skatelab.ru` с эмуляцией обрывов сети и вокруг upload-состояния, чтобы выявлять новые недоработки в mobile (`ChunkedUploader`/`UploadWorker`/queue) и backend (`uploads.py`). Каждую найденную недоработку → issue с тегом. Production-код не трогается (мандат: диагностика + тесты + issues).

Прогон: 2026-06-24, эмулятор `skatelab-emulator-2` (изолированный второй контейнер, ports 5556/5557), реальный backend `api.skatelab.ru`, debug APK, **en-US локаль** + **Private DNS off** (иначе app HTTP resolution падает с DNS-over-TLS breakdown).

## Preconditions

- **Backend:** `https://api.skatelab.ru/v1/` (реальный, живой; `uploads/init` endpoint подтверждён работает — 400 без query-param, но жив)
- **Аккаунт:** `test@skatelab.ru` / `Test123456` (`is_verified=true`)
- **Эмулятор:** `skatelab-emulator-2` (budtmo/docker-android:emulator_14.0, изолированный), Maestro 2.6.1
- **APK:** debug-сборка с `API_BASE_URL=https://api.skatelab.ru/v1/`
- **Asset:** `mobile/e2e/maestro/assets/test_video.mp4` (2.9MB)
- **Partials:** `login_as.yaml` (подход A), `pick_first_video.yaml` (исправлен: селектор `00:12` вместо `test_video` — photo-picker не показывает имя файла)
- **Локаль en-US** (для Maestro-селекторов): `adb shell service call locale 3 s16 ru.skatelab.capture s16 en-US`. ⚠️ Элемент-каталог остаётся ru (hardcoded — см. #331), селекторы используют "Аксель".
- **Private DNS off** (`adb shell settings put global private_dns_mode off`) — иначе DNS-over-TLS breakdown ломает app HTTP.

## Triage results

**Критический блокер #330 (upload-init зависает) делает upload-path unusable — все сценарии, требующие успешный upload-init, не доходят до своих проверок.**

| Flow | Сценарий | Статус | Issue | Примечание |
|------|----------|--------|-------|------------|
| u4-airplane-before-upload-baseline | airplane до upload → retry → complete (baseline) | **FAIL (blocker)** | **#330** | Baseline RED-by-#330: после "Next" app зависает на "Preparing upload…" (upload-init не доходит до HTTP, висит до `POST /uploads/init`). Ожидаемый "No connection"/"Uploading video…" не появляется. |
| u2-duplicate-upload | duplicate upload того же видео | **FAIL (blocker)** | **#330** | Online duplicate-upload: app зависает на "Preparing upload…" онлайн (без airplane) до HTTP. Не дошёл до duplicate-check. |
| u1-mid-upload-airplane-resume | airplane mid-upload → resume → complete | **BLOCKED** | #330 | Не прогонялся — упрётся в #330 (upload-init зависает до сетевого вызова). Прогнать после фикса #330. |
| u3-queue-airplane | queue с pending + обрыв | **BLOCKED** | #330 | Не прогонялся — упрётся в #330. Прогнать после фикса #330. |
| u5-upload-rate-limit | rate-limit edge | **BLOCKED** | #330 | Не прогонялся — упрётся в #330 (upload-init не доходит до `POST /uploads/init`, rate-limit не триггерится). Прогнать после фикса #330. |

## Найденные недоработки (новые)

### #330 — Upload-init зависает на "Preparing upload…" (критический блокер, prod-impact)
App висит на "Preparing upload…" **бесконечно** — и онлайн, и offline, **до отправки `POST /uploads/init`** (logcat: только успешный `GET /users/me`, upload-init-запроса нет). Backend жив (`uploads/init` endpoint отвечает). Root cause — подготовительная стадия upload-init (presign/multipart setup, чтение файла, или WorkManager-scheduling) зависает, не network-timeout. App unusable до force-stop.
- Flows: U4 (offline), U2 (online) — оба зависают на "Preparing upload…" после "Next".
- **Блокер для всех upload E2E**: U1/U3/U5 не могут пройти мимо upload-init.
- Fix (отдельным PR): upload-init preparation + timeout/recovery; при network-failure показывать "No connection"/"Retry".

### #331 — Элемент-каталог hardcoded ru, не i18n (E2E-инфра + i18n gap)
На экране "Select element" названия элементов hardcoded ru ("Аксель", "Сальхов", "Тулуп" и др.) — **не переводятся** при en-US локали (остальной UI en: "Camera", "Upload video", "Select element", "Next"). Нарушает i18n-принцип (no hardcoded user-facing strings). Ломает Maestro-селекторы (кириллица → "??????" в логах, хрупко); существующий `upload-pipeline.yaml` (`tapOn: "axel"`, en) **сломан**.
- Fix (отдельным PR): элемент-каталог в `strings.xml` (ru+en) + `stringResource()`; обновить Maestro-флоу на en-селекторы.

## Test-infra находки (не product-баги, не issues — зафиксировано для будущих прогонов)

- **Maestro mangles unicode ellipsis** `…` → `"Uploading video?"` (видно в логах). Селекторы с `…` хрупки — использовать regex/partial (`text: "Uploading video"`) или ждать en-i18n.
- **`pick_first_video.yaml` partial исправлен**: `tapOn: text: test_video` не работал (photo-picker не показывает имя файла) → `tapOn: text: "00:12"` (длительность, как `upload-pipeline.yaml`).
- **U-flows исправлены**: добавлен `tapOn: "Next"` после выбора элемента (app требует подтверждение "Next" перед upload-init) + ru-селектор "Аксель" (пока #331 не фикшен).
- **Private DNS breakdown** на эмуляторе (DNS-over-TLS `10.0.2.3` SSL-handshake fail) → `settings put global private_dns_mode off`. Симптом: ICMP ping работает, но app HTTP "Network error".
- **`pm clear` сбрасывает ВСЕ runtime-permissions** — re-grant CAMERA + BLUETOOTH_SCAN + BLUETOOTH_CONNECT, иначе BLE "find nearby devices" dialog блокирует flow.
- **Airplane-mode тогглинг** (Maestro `setAirplaneMode`) может сбросить WiFi — перед прогоном `svc wifi enable` + проверить `wifi_on=2`.
- **Второй эмулятор** `skatelab-emulator-2` (изолированный для параллельных прогонов) — boot ~8 мин, см. memory `second-android-emulator-setup`.

## Triage legend

- **PASS** — поверхность здорова
- **FAIL (blocker)** — RED из-за найденного блокер-бага → issue
- **BLOCKED** — не прогонялся, упрётся в блокер (#330) — прогнать после фикса
- **FLAKY** — единичный красный → не баг
- **SKIP** — пропуск с причиной

## Что делать после фикса #330

1. Прогнать U1 (mid-upload airplane resume), U3 (queue+airplane), U5 (rate-limit) — сейчас BLOCKED.
2. После фикса #331 (i18n en): заменить ru-селекторы "Аксель" → "axel" в U-flows + существующем `upload-pipeline.yaml`.
3. Тогда Maestro-логи станут читаемы (без "??????").